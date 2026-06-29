"""KB e2e fixtures and helpers — owned exclusively by e2e-kb-chain."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import re
import socket
import sqlite3
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.e2e._entrypoint_smoke import (
    child_env,
    repo_root,
    reserve_port,
    run_command,
    running_process,
    wait_for_condition,
    wait_for_http_ready,
)
from tests.e2e._path_helpers import agent_home_dir, agent_state_db_path
from tests.e2e.conftest import _admin_session_headers, _agent_status
from tests.integration._migration_template import apply_migrations

# Unique sentinel phrase used as KB content — easy to grep in LLM stub requests.
KB_BEACON_TEXT = (
    "The secret activation code for this test is XKCD-4242. "
    "This sentinel phrase uniquely identifies KB injection in agent context."
)
KB_BEACON_KEYWORD = "XKCD-4242"

_TENANT_ID = "default"
_KB_ID = "e2e-kb"
_AGENT_NAME = "kb-support"
_SERVICE_KEY_RE = re.compile(r"service_key:\s*(ma-[0-9a-f]+)")


@dataclass(frozen=True)
class ManagedKBStack:
    platform_url: str
    node_id: str
    agent_id: int
    agent_name: str
    admin_session_headers: dict[str, str]
    home_dir: Path
    db_path: Path
    kb_id: str
    tenant_id: str
    # The llm_stub /v1 base URL — append /requests to read recorded calls.
    stub_v1_url: str
    kb_service_url: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _seed_agent_with_kb(
    home_dir: Path,
    llm_stub_v1_url: str,
    node_id: str,
    *,
    config_overrides: dict[str, Any] | None = None,
) -> tuple[int, str]:
    """Create agent + KB record + KB-agent binding; materialize agent.yaml."""
    from fleetent import agent_store
    from fleetent.knowledge_base.management.runtime import create_knowledge_base as kb_create
    from fleetent.platform.agent_lifecycle import credential_slots, materialize, secret_store
    from fleetent.platform.knowledge_base_management import agent_kbs_store
    from fleetent.platform.model_provider_management import provider_admin_store
    from fleetent.platform.node_management import placement_store

    provider_admin_store.add_provider(
        "kb-stub-provider",
        llm_stub_v1_url,
        "stub-model",
        provider="openai",
        protocol="openai_chat",
        api_key_env="FLEETENT_AGENT_KB_SUPPORT_MODEL",
    )
    agent = agent_store.create_agent(
        _AGENT_NAME,
        "You are a helpful knowledge base assistant.",
        [],
        model_overrides={"default": [{"provider_id": "kb-stub-provider"}]},
        config_overrides=config_overrides,
    )
    credential_slots.ensure_slot(
        agent,
        "env:FLEETENT_AGENT_KB_SUPPORT_MODEL",
        mode="inject",
        env_name="FLEETENT_AGENT_KB_SUPPORT_MODEL",
    )
    secret_store.set(agent.id, "FLEETENT_AGENT_KB_SUPPORT_MODEL", "sk-e2e-kb-stub", "e2e")

    # Create the KB record in the tenant-scoped kb.db under Fleetent home.
    kb_scope = _open_kb_scope(home_dir)
    kb_create(_TENANT_ID, _KB_ID, "E2E test KB", database=kb_scope.kb_db)

    # Bind KB to agent (management DB).
    agent_kbs_store.bind(_TENANT_ID, _KB_ID, agent.id)

    # Materialize agent.yaml — now includes KB bindings from agent_kbs_store.
    materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)
    placement_store.pin_agent(agent.id, node_id)
    return agent.id, agent.name


def _open_kb_scope(home_dir: Path):  # type: ignore[return]
    """Open (and migrate) the per-tenant KB scope under Fleetent home root."""
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend

    scope = SQLiteTenantBackend(data_dir=home_dir).resolve(_TENANT_ID)
    scope.open_kb_db(KB_MIGRATIONS)
    return scope


async def _pre_ingest(home_dir: Path) -> None:
    """Ingest KB_BEACON_TEXT into the per-tenant KB before the stack starts."""
    from fleetent.config import KnowledgeBaseSettings
    from fleetent.knowledge_base import runtime as kb_runtime
    from fleetent.knowledge_base.ingest.runtime import ingest_text

    scope = _open_kb_scope(home_dir)
    old_db = kb_runtime._kb_db
    old_backend = kb_runtime._kb_vector_backend
    try:
        kb_runtime.set_database(scope.kb_db)
        kb_runtime.set_vector_backend(scope.kb_vector_backend)
        await ingest_text(
            filename="beacon.txt",
            content=KB_BEACON_TEXT,
            tenant_id=_TENANT_ID,
            kb_id=_KB_ID,
            source="e2e-test",
            source_url=None,
            settings=KnowledgeBaseSettings(),
            database=scope.kb_db,
        )
    finally:
        kb_runtime.set_database(old_db)
        kb_runtime.set_vector_backend(old_backend)


def _write_kb_service_config(path: Path, *, home_dir: Path, port: int) -> None:
    import yaml

    path.write_text(
        yaml.safe_dump(
            {
                "service": {
                    "tenant_id": _TENANT_ID,
                    "service_key_ref": "env:FLEENTENT_KB_SERVICE_KEY".replace(
                        "FLEENTENT", "FLEETENT"
                    ),
                    "host": "127.0.0.1",
                    "port": port,
                },
                "data": {"home": "."},
                "retrieval": {"default_mode": "hybrid", "top_k": 10},
                "embedding": {
                    "endpoint": "http://embedder.invalid/v1/embeddings",
                    "model": "kb-embed-stub",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _register_node_platform_cli(*, env: dict[str, str], node_id: str) -> str:
    result = run_command(
        [
            sys.executable,
            "-m",
            "fleetent",
            "platform",
            "node",
            "register",
            node_id,
            "--name",
            "KB E2E Node",
        ],
        env=env,
        cwd=repo_root(),
    )
    if result.returncode != 0:
        raise AssertionError(
            f"node register failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    match = _SERVICE_KEY_RE.search(result.stdout)
    if match is None:
        raise AssertionError(f"could not parse node service key:\n{result.stdout}")
    return match.group(1)


# ---------------------------------------------------------------------------
# Public helpers for tests
# ---------------------------------------------------------------------------


def read_kb_retrieval_traces(home_dir: Path, agent_name: str) -> list[dict[str, Any]]:
    """Read kb_retrieval trace events from the agent's state DB (raw SQLite)."""
    state_db_path = agent_state_db_path(home_dir, agent_name, tenant_id=_TENANT_ID)
    if not state_db_path.exists():
        return []
    conn = sqlite3.connect(str(state_db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT payload_json FROM traces WHERE event_type = 'kb_retrieval'"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def wait_for_kb_trace(
    home_dir: Path,
    agent_name: str,
    *,
    timeout: float = 10.0,
    interval: float = 0.3,
) -> list[dict[str, Any]]:
    """Poll until at least one kb_retrieval trace appears; raise on timeout."""

    def _check() -> list[dict[str, Any]] | None:
        rows = read_kb_retrieval_traces(home_dir, agent_name)
        return rows if rows else None

    return wait_for_condition(  # type: ignore[return-value]
        _check,
        timeout=timeout,
        interval=interval,
        description="kb_retrieval trace in agent state DB",
    )


def get_stub_requests(stub_v1_url: str) -> list[dict[str, Any]]:
    """Fetch all recorded LLM requests from the stub server."""
    resp = httpx.get(f"{stub_v1_url}/requests", timeout=5.0)
    resp.raise_for_status()
    return list(resp.json())


def clear_stub_requests(stub_v1_url: str) -> None:
    httpx.delete(f"{stub_v1_url}/requests", timeout=5.0).raise_for_status()


def find_system_messages_containing(stub_requests: list[dict[str, Any]], keyword: str) -> list[str]:
    """Return system message contents that include keyword, across all recorded requests."""
    hits: list[str] = []
    for req in stub_requests:
        for msg in req.get("messages", []):
            if msg.get("role") == "system":
                content = msg.get("content") or ""
                if keyword in content:
                    hits.append(content)
    return hits


def _wait_for_port_free(port: int, timeout: float = 20.0) -> None:
    """Block until port can be bound (= safe for the next server to use)."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return  # bind succeeded = port is available
            except OSError:
                pass  # EADDRINUSE = something still holds the socket
        time.sleep(0.5)
    raise AssertionError(f"port {port} still occupied after {timeout}s")


def _wait_for_agent_chat_ready(
    platform_url: str,
    agent_name: str,
    headers: dict[str, str],
    timeout: float = 30.0,
) -> None:
    """Poll until the agent's HTTP server actually responds to a chat request."""

    def _probe():
        try:
            with httpx.stream(
                "POST",
                f"{platform_url}/admin/agents/{agent_name}/chat",
                headers=headers,
                json={"message": "ping"},
                timeout=5.0,
            ) as r:
                b"".join(r.iter_bytes())
                # Accept only 200; 401 means old/stale forwarder, 5xx means not ready yet.
                return True if r.status_code == 200 else None
        except Exception:
            return None

    wait_for_condition(_probe, timeout=timeout, interval=1.0, description="agent HTTP ready")


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def managed_kb_stack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    llm_stub_base_url: str,
) -> Iterator[ManagedKBStack]:
    """Multi-process managed stack with a KB pre-bound and pre-populated."""
    home_dir = tmp_path / "fleetent-home"
    home_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "management.db"
    apply_migrations(db_path)

    secret_key = base64.urlsafe_b64encode(b"9" * 32).decode("ascii")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLEETENT_HOME", str(home_dir))
    monkeypatch.setenv("FLEETENT_SECRET_KEY", secret_key)

    node_id = "node-e2e-kb"
    common_env = child_env(
        extra={
            "DATABASE_URL": f"sqlite:///{db_path}",
            "FLEETENT_HOME": str(home_dir),
            "FLEETENT_SECRET_KEY": secret_key,
            "FLEETENT_FORWARDER_HOST_OVERRIDE": "127.0.0.1",
        }
    )

    node_service_key = _register_node_platform_cli(env=common_env, node_id=node_id)
    agent_id, agent_name = _seed_agent_with_kb(
        home_dir=home_dir,
        llm_stub_v1_url=llm_stub_base_url,
        node_id=node_id,
    )

    # Pre-populate KB before node/agent start so the agent boots with data ready.
    asyncio.run(_pre_ingest(home_dir=home_dir))

    platform_port = reserve_port()
    platform_url = f"http://127.0.0.1:{platform_port}"
    platform_argv = [
        sys.executable,
        "-m",
        "uvicorn",
        "fleetent.server:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(platform_port),
        "--log-level",
        "warning",
    ]
    node_env = {
        **common_env,
        "FLEETENT_NODE_PLATFORM_URL": platform_url,
        "FLEETENT_NODE_ID": node_id,
        "FLEETENT_NODE_SERVICE_KEY": node_service_key,
        "FLEETENT_NODE_INTERVAL_SECONDS": "1",
    }
    node_argv = [sys.executable, "-m", "fleetent", "node", "start"]

    from fleetent.node.forwarder_contract import DEFAULT_FORWARDER_PORT

    with contextlib.ExitStack() as stack:
        platform_proc = stack.enter_context(
            running_process(platform_argv, env=common_env, cwd=repo_root())
        )
        wait_for_http_ready(platform_proc, f"{platform_url}/health", timeout=20.0)
        # Wait for the forwarder port to be free — a previous test's node may still be
        # draining its socket after SIGTERM; without this check the new node fails to bind.
        _wait_for_port_free(DEFAULT_FORWARDER_PORT)
        stack.enter_context(running_process(node_argv, env=node_env, cwd=repo_root()))
        wait_for_condition(
            lambda: _agent_status(agent_id=agent_id, node_id=node_id),
            timeout=30.0,
            interval=0.5,
            description="kb-support agent healthy",
        )
        admin_headers = _admin_session_headers(platform_url)
        # Also wait for the agent's HTTP server to accept requests (PID-alive ≠ HTTP-ready).
        _wait_for_agent_chat_ready(platform_url, agent_name, admin_headers)
        try:
            yield ManagedKBStack(
                platform_url=platform_url,
                node_id=node_id,
                agent_id=agent_id,
                agent_name=agent_name,
                admin_session_headers=admin_headers,
                home_dir=home_dir,
                db_path=db_path,
                kb_id=_KB_ID,
                tenant_id=_TENANT_ID,
                stub_v1_url=llm_stub_base_url,
            )
        finally:
            agent_home = agent_home_dir(home_dir, agent_name, tenant_id=_TENANT_ID)
            if agent_home.exists():
                stop = run_command(
                    [
                        sys.executable,
                        "-m",
                        "fleetent",
                        "agent",
                        "stop",
                        agent_name,
                        "--home",
                        str(agent_home),
                    ],
                    env=common_env,
                    cwd=repo_root(),
                )
                if stop.returncode not in (0, 1):
                    raise AssertionError(
                        "kb-support agent stop failed\n"
                        f"stdout:\n{stop.stdout}\nstderr:\n{stop.stderr}"
                    )


@pytest.fixture
def managed_kb_http_stack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    llm_stub_base_url: str,
) -> Iterator[ManagedKBStack]:
    """Managed stack + standalone kb-serve process + agent http provider override."""
    home_dir = tmp_path / "fleetent-home"
    home_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "management.db"
    apply_migrations(db_path)

    secret_key = base64.urlsafe_b64encode(b"8" * 32).decode("ascii")
    kb_service_key = "svc-e2e-kb-http"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLEETENT_HOME", str(home_dir))
    monkeypatch.setenv("FLEETENT_SECRET_KEY", secret_key)
    monkeypatch.setenv("FLEETENT_KB_SERVICE_KEY", kb_service_key)

    node_id = "node-e2e-kb-http"
    kb_service_port = reserve_port()
    kb_service_url = f"http://127.0.0.1:{kb_service_port}/search"
    common_env = child_env(
        extra={
            "DATABASE_URL": f"sqlite:///{db_path}",
            "FLEETENT_HOME": str(home_dir),
            "FLEETENT_SECRET_KEY": secret_key,
            "FLEETENT_FORWARDER_HOST_OVERRIDE": "127.0.0.1",
            "FLEETENT_KB_SERVICE_KEY": kb_service_key,
        }
    )

    node_service_key = _register_node_platform_cli(env=common_env, node_id=node_id)
    agent_id, agent_name = _seed_agent_with_kb(
        home_dir=home_dir,
        llm_stub_v1_url=llm_stub_base_url,
        node_id=node_id,
        config_overrides={
            "knowledge": {
                "provider": {
                    "type": "http",
                    "url": kb_service_url,
                    "auth_ref": "env:FLEETENT_KB_SERVICE_KEY",
                }
            }
        },
    )

    asyncio.run(_pre_ingest(home_dir=home_dir))

    kb_service_config = home_dir / "kb-service.yaml"
    _write_kb_service_config(kb_service_config, home_dir=home_dir, port=kb_service_port)

    platform_port = reserve_port()
    platform_url = f"http://127.0.0.1:{platform_port}"
    platform_argv = [
        sys.executable,
        "-m",
        "uvicorn",
        "fleetent.server:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(platform_port),
        "--log-level",
        "warning",
    ]
    kb_serve_argv = [
        sys.executable,
        "-m",
        "fleetent",
        "kb-serve",
        "--config",
        str(kb_service_config),
    ]
    node_env = {
        **common_env,
        "FLEETENT_NODE_PLATFORM_URL": platform_url,
        "FLEETENT_NODE_ID": node_id,
        "FLEETENT_NODE_SERVICE_KEY": node_service_key,
        "FLEETENT_NODE_INTERVAL_SECONDS": "1",
    }
    node_argv = [sys.executable, "-m", "fleetent", "node", "start"]

    from fleetent.node.forwarder_contract import DEFAULT_FORWARDER_PORT

    with contextlib.ExitStack() as stack:
        platform_proc = stack.enter_context(
            running_process(platform_argv, env=common_env, cwd=repo_root())
        )
        wait_for_http_ready(platform_proc, f"{platform_url}/health", timeout=20.0)
        kb_serve_proc = stack.enter_context(
            running_process(kb_serve_argv, env=common_env, cwd=repo_root())
        )
        wait_for_http_ready(
            kb_serve_proc,
            f"http://127.0.0.1:{kb_service_port}/healthz",
            timeout=20.0,
        )
        _wait_for_port_free(DEFAULT_FORWARDER_PORT)
        stack.enter_context(running_process(node_argv, env=node_env, cwd=repo_root()))
        wait_for_condition(
            lambda: _agent_status(agent_id=agent_id, node_id=node_id),
            timeout=30.0,
            interval=0.5,
            description="kb-support http-provider agent healthy",
        )
        admin_headers = _admin_session_headers(platform_url)
        try:
            yield ManagedKBStack(
                platform_url=platform_url,
                node_id=node_id,
                agent_id=agent_id,
                agent_name=agent_name,
                admin_session_headers=admin_headers,
                home_dir=home_dir,
                db_path=db_path,
                kb_id=_KB_ID,
                tenant_id=_TENANT_ID,
                stub_v1_url=llm_stub_base_url,
                kb_service_url=kb_service_url,
            )
        finally:
            agent_home = agent_home_dir(home_dir, agent_name, tenant_id=_TENANT_ID)
            if agent_home.exists():
                stop = run_command(
                    [
                        sys.executable,
                        "-m",
                        "fleetent",
                        "agent",
                        "stop",
                        agent_name,
                        "--home",
                        str(agent_home),
                    ],
                    env=common_env,
                    cwd=repo_root(),
                )
                if stop.returncode not in (0, 1):
                    raise AssertionError(
                        "kb-support http-provider agent stop failed\n"
                        f"stdout:\n{stop.stdout}\nstderr:\n{stop.stderr}"
                    )
