from __future__ import annotations

import base64
import contextlib
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

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
from tests.e2e._path_helpers import agent_home_dir
from tests.integration._migration_template import apply_migrations

_SERVICE_KEY_RE = re.compile(r"service_key:\s*(ma-[0-9a-f]+)")


@dataclass(frozen=True)
class ManagedStack:
    platform_url: str
    node_id: str
    agent_id: int
    agent_name: str
    agent_status: dict[str, object]
    admin_session_headers: dict[str, str]
    desired_state_cache_path: Path
    home_dir: Path
    db_path: Path


@pytest.fixture
def llm_stub_base_url() -> Iterator[str]:
    port = reserve_port()
    argv = [
        sys.executable,
        "-m",
        "uvicorn",
        "tests.e2e._llm_stub:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    with running_process(argv, env=child_env(extra={}), cwd=repo_root()) as proc:
        wait_for_http_ready(proc, f"http://127.0.0.1:{port}/health", timeout=10.0)
        yield f"http://127.0.0.1:{port}/v1"


def _register_node(*, env: dict[str, str], node_id: str) -> str:
    result = run_command(
        [
            sys.executable,
            "-m",
            "fleetent",
            "admin",
            "node",
            "register",
            node_id,
            "--name",
            "E2E Node",
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
        raise AssertionError(f"could not parse node service key from output:\n{result.stdout}")
    return match.group(1)


def _seed_managed_agent(*, llm_stub_base_url: str, node_id: str) -> tuple[int, str]:
    from fleetent import agent_store
    from fleetent.platform.agent_lifecycle import credential_slots, materialize, secret_store
    from fleetent.platform.model_provider_management import provider_admin_store
    from fleetent.platform.node_management import placement_store

    provider_admin_store.add_provider(
        "stub-provider",
        llm_stub_base_url,
        "stub-model",
        provider="openai",
        protocol="openai_chat",
        api_key_env="FLEETENT_AGENT_SUPPORT_MODEL",
    )
    agent = agent_store.create_agent(
        "support",
        "You are the managed stack support agent.",
        [],
        model_overrides={"default": [{"provider_id": "stub-provider"}]},
    )
    credential_slots.ensure_slot(
        agent,
        "env:FLEETENT_AGENT_SUPPORT_MODEL",
        mode="inject",
        env_name="FLEETENT_AGENT_SUPPORT_MODEL",
    )
    secret_store.set(agent.id, "FLEETENT_AGENT_SUPPORT_MODEL", "sk-e2e-stub", "e2e")
    materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)
    placement_store.pin_agent(agent.id, node_id)
    return agent.id, agent.name


def _agent_status(*, agent_id: int, node_id: str) -> dict[str, object] | None:
    from fleetent.platform.node_management import node_store

    for row in node_store.list_agent_status_by_node(node_id):
        if int(row["agent_id"]) == agent_id and row.get("health") == "healthy":
            return dict(row)
    return None


def _admin_session_headers(platform_url: str) -> dict[str, str]:
    password = "admin"
    response = httpx.post(
        f"{platform_url}/admin/login",
        json={"email": "admin", "password": password},
        timeout=5.0,
    )
    response.raise_for_status()
    token = str(response.json()["token"])
    if response.json().get("must_reset"):
        new_password = "admin-reset-123"
        changed = httpx.post(
            f"{platform_url}/admin/change-password",
            headers={"Authorization": f"Session {token}"},
            json={"new_password": new_password},
            timeout=5.0,
        )
        changed.raise_for_status()
        relogin = httpx.post(
            f"{platform_url}/admin/login",
            json={"email": "admin", "password": new_password},
            timeout=5.0,
        )
        relogin.raise_for_status()
        token = str(relogin.json()["token"])
    return {"Authorization": f"Session {token}"}


@pytest.fixture
def managed_stack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    llm_stub_base_url: str,
) -> Iterator[ManagedStack]:
    home_dir = tmp_path / "fleetent-home"
    home_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "management.db"
    apply_migrations(db_path)

    secret_key = base64.urlsafe_b64encode(b"9" * 32).decode("ascii")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLEETENT_HOME", str(home_dir))
    monkeypatch.setenv("FLEETENT_SECRET_KEY", secret_key)

    node_id = "node-e2e"
    common_env = child_env(
        extra={
            "DATABASE_URL": f"sqlite:///{db_path}",
            "FLEETENT_HOME": str(home_dir),
            "FLEETENT_SECRET_KEY": secret_key,
            "FLEETENT_FORWARDER_HOST_OVERRIDE": "127.0.0.1",
        }
    )
    node_service_key = _register_node(env=common_env, node_id=node_id)
    agent_id, agent_name = _seed_managed_agent(llm_stub_base_url=llm_stub_base_url, node_id=node_id)
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

    with contextlib.ExitStack() as stack:
        platform_proc = stack.enter_context(
            running_process(platform_argv, env=common_env, cwd=repo_root())
        )
        wait_for_http_ready(platform_proc, f"{platform_url}/health", timeout=20.0)
        stack.enter_context(running_process(node_argv, env=node_env, cwd=repo_root()))
        status = wait_for_condition(
            lambda: _agent_status(agent_id=agent_id, node_id=node_id),
            timeout=30.0,
            interval=0.5,
            description="managed agent healthy status",
        )
        admin_session_headers = _admin_session_headers(platform_url)
        try:
            yield ManagedStack(
                platform_url=platform_url,
                node_id=node_id,
                agent_id=agent_id,
                agent_name=agent_name,
                agent_status=status,
                admin_session_headers=admin_session_headers,
                desired_state_cache_path=home_dir / "node" / "desired-state-cache.json",
                home_dir=home_dir,
                db_path=db_path,
            )
        finally:
            agent_home = agent_home_dir(home_dir, agent_name)
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
                        "managed agent stop failed during teardown\n"
                        f"stdout:\n{stop.stdout}\n"
                        f"stderr:\n{stop.stderr}"
                    )
