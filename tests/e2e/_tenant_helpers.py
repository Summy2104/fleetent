"""Multi-tenant managed-stack fixture for e2e isolation tests.

Provides ``managed_stack_two_tenants`` — starts ONE node with TWO agents,
each belonging to a distinct tenant.  Reuses the existing entrypoint helpers
and conftest ``llm_stub_base_url`` fixture; never touches ``managed_stack``.
"""

from __future__ import annotations

import base64
import contextlib
import re
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.e2e._entrypoint_smoke import (
    child_env,
    repo_root,
    reserve_port,
    run_command,
    running_process,
    wait_for_http_ready,
)
from tests.e2e._path_helpers import agent_home_dir
from tests.integration._migration_template import apply_migrations


@dataclass(frozen=True)
class TwoTenantStack:
    platform_url: str
    node_id: str
    agent_a_id: int
    agent_a_name: str
    agent_a_status: dict[str, object]
    agent_b_id: int
    agent_b_name: str
    agent_b_status: dict[str, object]
    tenant_a_id: str
    tenant_b_id: str
    admin_session_headers: dict[str, str]
    home_dir: Path
    db_path: Path


_SERVICE_KEY_RE = re.compile(r"service_key:\s*(ma-[0-9a-f]+)")


# ---------------------------------------------------------------------------
# Internal helpers (mirror conftest.py private helpers, not imported from it)
# ---------------------------------------------------------------------------


def _register_node_mt(*, env: dict[str, str], node_id: str) -> str:
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
            "MT E2E Node",
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


def _setup_provider_and_tenants(
    *, llm_stub_base_url: str, tenant_a_id: str, tenant_b_id: str
) -> None:
    from fleetent.platform.model_provider_management import provider_admin_store
    from fleetent.platform.tenancy import store as tenancy_store

    provider_admin_store.add_provider(
        "stub-provider-mt",
        llm_stub_base_url,
        "stub-model",
        provider="openai",
        protocol="openai_chat",
        api_key_env="FLEETENT_AGENT_MODEL_MT",
    )
    tenancy_store.create_tenant(id=tenant_a_id, name=f"E2E Tenant {tenant_a_id}", status="active")
    tenancy_store.create_tenant(id=tenant_b_id, name=f"E2E Tenant {tenant_b_id}", status="active")


def _seed_tenant_agent(name: str, *, tenant_id: str, node_id: str) -> tuple[int, str]:
    from fleetent import agent_store
    from fleetent.platform.agent_lifecycle import credential_slots, materialize, secret_store
    from fleetent.platform.node_management import placement_store

    agent = agent_store.create_agent(
        name,
        f"You are the {name} managed-stack agent.",
        [],
        tenant_id=tenant_id,
        model_overrides={"default": [{"provider_id": "stub-provider-mt"}]},
    )
    credential_slots.ensure_slot(
        agent,
        "env:FLEETENT_AGENT_MODEL_MT",
        mode="inject",
        env_name="FLEETENT_AGENT_MODEL_MT",
    )
    secret_store.set(agent.id, "FLEETENT_AGENT_MODEL_MT", "sk-e2e-stub", "e2e")
    materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)
    placement_store.pin_agent(agent.id, node_id)
    return agent.id, agent.name


def _agent_status_mt(*, agent_id: int, node_id: str) -> dict[str, object] | None:
    from fleetent.platform.node_management import node_store

    for row in node_store.list_agent_status_by_node(node_id):
        if int(row["agent_id"]) == agent_id and row.get("health") == "healthy":
            return dict(row)
    return None


def _admin_session_headers_mt(platform_url: str) -> dict[str, str]:
    import httpx

    password = "admin"
    response = httpx.post(
        f"{platform_url}/admin/login",
        json={"email": "admin", "password": password},
        timeout=5.0,
    )
    response.raise_for_status()
    token = str(response.json()["token"])
    if response.json().get("must_reset"):
        new_password = "admin-reset-mt-123"
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


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def managed_stack_two_tenants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    llm_stub_base_url: str,
) -> Iterator[TwoTenantStack]:
    """Start platform + node + two tenant agents; yield TwoTenantStack; teardown both."""
    home_dir = tmp_path / "fleetent-home"
    home_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "management.db"
    apply_migrations(db_path)

    secret_key = base64.urlsafe_b64encode(b"9" * 32).decode("ascii")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLEETENT_HOME", str(home_dir))
    monkeypatch.setenv("FLEETENT_SECRET_KEY", secret_key)

    node_id = "node-e2e-mt"
    common_env = child_env(
        extra={
            "DATABASE_URL": f"sqlite:///{db_path}",
            "FLEETENT_HOME": str(home_dir),
            "FLEETENT_SECRET_KEY": secret_key,
            "FLEETENT_FORWARDER_HOST_OVERRIDE": "127.0.0.1",
        }
    )

    node_service_key = _register_node_mt(env=common_env, node_id=node_id)

    _setup_provider_and_tenants(
        llm_stub_base_url=llm_stub_base_url, tenant_a_id="tenant-a", tenant_b_id="tenant-b"
    )
    agent_a_id, agent_a_name = _seed_tenant_agent(
        "mt-agent-a", tenant_id="tenant-a", node_id=node_id
    )
    agent_b_id, agent_b_name = _seed_tenant_agent(
        "mt-agent-b", tenant_id="tenant-b", node_id=node_id
    )

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

        # Poll both agents in a shared deadline; the node starts them sequentially
        # so agent-b may not be healthy until well after agent-a.
        _deadline = time.monotonic() + 90.0
        _status_a: dict[str, object] | None = None
        _status_b: dict[str, object] | None = None
        while time.monotonic() < _deadline:
            if _status_a is None:
                _status_a = _agent_status_mt(agent_id=agent_a_id, node_id=node_id)
            if _status_b is None:
                _status_b = _agent_status_mt(agent_id=agent_b_id, node_id=node_id)
            if _status_a is not None and _status_b is not None:
                break
            time.sleep(0.5)
        else:
            raise AssertionError(
                "timed out waiting for both agents to be healthy "
                f"(a_ready={_status_a is not None}, b_ready={_status_b is not None})"
            )
        status_a: dict[str, object] = _status_a  # type: ignore[assignment]
        status_b: dict[str, object] = _status_b  # type: ignore[assignment]

        admin_headers = _admin_session_headers_mt(platform_url)
        try:
            yield TwoTenantStack(
                platform_url=platform_url,
                node_id=node_id,
                agent_a_id=agent_a_id,
                agent_a_name=agent_a_name,
                agent_a_status=status_a,
                agent_b_id=agent_b_id,
                agent_b_name=agent_b_name,
                agent_b_status=status_b,
                tenant_a_id="tenant-a",
                tenant_b_id="tenant-b",
                admin_session_headers=admin_headers,
                home_dir=home_dir,
                db_path=db_path,
            )
        finally:
            for name in (agent_a_name, agent_b_name):
                tenant_id = "tenant-a" if name == agent_a_name else "tenant-b"
                agent_home = agent_home_dir(home_dir, name, tenant_id=tenant_id)
                if agent_home.exists():
                    stop = run_command(
                        [
                            sys.executable,
                            "-m",
                            "fleetent",
                            "agent",
                            "stop",
                            name,
                            "--home",
                            str(agent_home),
                        ],
                        env=common_env,
                        cwd=repo_root(),
                    )
                    if stop.returncode not in (0, 1):
                        raise AssertionError(
                            f"agent {name} stop failed during teardown\n"
                            f"stdout:\n{stop.stdout}\nstderr:\n{stop.stderr}"
                        )
