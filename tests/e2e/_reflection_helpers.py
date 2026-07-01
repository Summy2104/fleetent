from __future__ import annotations

import base64
import contextlib
import json
import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from fleetent.identity import Principal, encode_ingress_principal
from tests.e2e._entrypoint_smoke import (
    child_env,
    repo_root,
    reserve_port,
    run_command,
    running_process,
    wait_for_condition,
    wait_for_http_ready,
)
from tests.e2e._im_helpers import managed_agent_route_server
from tests.e2e._path_helpers import agent_home_dir, agent_state_db_path
from tests.e2e.conftest import _admin_session_headers, _agent_status, _register_node
from tests.integration._migration_template import apply_migrations


@dataclass(frozen=True)
class ReflectionManagedStack:
    platform_url: str
    node_id: str
    node_service_key: str
    agent_id: int
    agent_name: str
    agent_pid: int
    admin_session_headers: dict[str, str]
    agent_home: Path
    agent_state_db: Path
    home_dir: Path
    db_path: Path
    common_env: dict[str, str]


@contextlib.contextmanager
def managed_reflection_stack(
    *,
    auto_apply: bool = False,
    interval_seconds: float = 0.5,
) -> Iterator[ReflectionManagedStack]:
    import tempfile

    previous_env = {key: os.environ.get(key) for key in _ENV_KEYS}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home_dir = tmp_path / "fleetent-home"
            home_dir.mkdir(parents=True, exist_ok=True)
            db_path = tmp_path / "management.db"
            apply_migrations(db_path)

            secret_key = base64.urlsafe_b64encode(b"9" * 32).decode("ascii")
            os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
            os.environ["FLEETENT_HOME"] = str(home_dir)
            os.environ["FLEETENT_SECRET_KEY"] = secret_key

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

            llm_port = reserve_port()
            llm_argv = [
                sys.executable,
                "-m",
                "uvicorn",
                "tests.e2e._llm_stub:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(llm_port),
                "--log-level",
                "warning",
            ]

            with contextlib.ExitStack() as stack:
                llm_proc = stack.enter_context(
                    running_process(llm_argv, env=child_env(extra={}), cwd=repo_root())
                )
                wait_for_http_ready(llm_proc, f"http://127.0.0.1:{llm_port}/health", timeout=10.0)
                llm_stub_base_url = f"http://127.0.0.1:{llm_port}/v1"

                agent_id, agent_name = _seed_reflection_agent(
                    llm_stub_base_url=llm_stub_base_url,
                    node_id=node_id,
                    auto_apply=auto_apply,
                    interval_seconds=interval_seconds,
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

                platform_proc = stack.enter_context(
                    running_process(platform_argv, env=common_env, cwd=repo_root())
                )
                wait_for_http_ready(platform_proc, f"{platform_url}/health", timeout=20.0)
                stack.enter_context(running_process(node_argv, env=node_env, cwd=repo_root()))
                status = wait_for_condition(
                    lambda: _agent_status(agent_id=agent_id, node_id=node_id),
                    timeout=30.0,
                    interval=0.5,
                    description="managed reflection agent healthy status",
                )

                agent_home = agent_home_dir(home_dir, agent_name)
                yield ReflectionManagedStack(
                    platform_url=platform_url,
                    node_id=node_id,
                    node_service_key=node_service_key,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    agent_pid=int(status["pid"]),
                    admin_session_headers=_admin_session_headers(platform_url),
                    agent_home=agent_home,
                    agent_state_db=agent_state_db_path(home_dir, agent_name),
                    home_dir=home_dir,
                    db_path=db_path,
                    common_env=common_env,
                )

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
                        "managed reflection agent stop failed during teardown\n"
                        f"stdout:\n{stop.stdout}\n"
                        f"stderr:\n{stop.stderr}"
                    )
    finally:
        _restore_env(previous_env)


def wait_for_reflection_report() -> dict[str, object]:
    with managed_reflection_stack() as stack:
        return wait_for_condition(
            lambda: _latest_reflection_report(stack.agent_state_db),
            timeout=10.0,
            interval=0.5,
            description="reflection scheduler report",
        )


def seed_memory_stale_proposal(
    stack: ReflectionManagedStack,
    *,
    risk: str = "medium",
) -> dict[str, str]:
    script = f"""
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fleetent import agent_config, reflection
from fleetent.memory import store as memory_store
from fleetent.memory.models import MemoryItem
from fleetent.runtime.agent_app import _init_agent_db_schema

agent_home = (
    Path(os.environ["FLEETENT_HOME"])
    / "tenants"
    / "default"
    / "agents"
    / "{stack.agent_name}"
)
agent = agent_config.scan_home(agent_home)
_init_agent_db_schema(agent_home / "data", agent_name=agent.name, tenant_id=agent.tenant_id)
now = datetime.now(UTC).replace(microsecond=0)
memory_id = str(uuid.uuid4())
memory_store.insert_memory(
    MemoryItem(
        id=memory_id,
        user_id=agent.name,
        type="context",
        content="User is currently triaging reflection e2e coverage",
        created_at=now,
        updated_at=now,
        expires_at=None,
    )
)
proposal = reflection.create_memory_maintenance_proposal(
    user_id=agent.name,
    action="mark_stale",
    target_memory_ids=[memory_id],
    proposed_content=None,
    risk="{risk}",
    reason="e2e seed mark_stale proposal",
    evidence_ids=["e2e-seed"],
)
print(json.dumps({{"proposal_id": proposal.id, "memory_id": memory_id}}))
"""
    return _run_agent_side_script(stack, script)


def approve_reflection_proposal_via_im(
    stack: ReflectionManagedStack,
    *,
    proposal_id: str,
    user_id: str,
) -> None:
    token = _agent_tui_token(stack.agent_home)
    with managed_agent_route_server(stack) as base_url:  # type: ignore[arg-type]
        response = httpx.post(
            f"{base_url}/im/route",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Fleetent-Principal": encode_ingress_principal(
                    Principal(user_id=user_id, tenant_id="default")
                ),
            },
            json={
                "platform": "slack",
                "session_id": f"approval-{proposal_id}",
                "user_id": user_id,
                "text": f"approve {proposal_id}",
                "agent_name": stack.agent_name,
            },
            timeout=10.0,
        )
        response.raise_for_status()


def wait_for_memory_proposal_applied(
    stack: ReflectionManagedStack,
    *,
    proposal_id: str,
    memory_id: str,
) -> dict[str, object]:
    return wait_for_condition(
        lambda: _memory_apply_state(
            stack.agent_state_db, proposal_id=proposal_id, memory_id=memory_id
        ),
        timeout=10.0,
        interval=0.5,
        description="memory proposal applied state",
    )


def seed_skill_reflection_traces(stack: ReflectionManagedStack, *, pattern: str) -> None:
    script = f"""
import os
from pathlib import Path

from fleetent import agent_config, observability
from fleetent.runtime.agent_app import _init_agent_db_schema

agent_home = (
    Path(os.environ["FLEETENT_HOME"])
    / "tenants"
    / "default"
    / "agents"
    / "{stack.agent_name}"
)
agent = agent_config.scan_home(agent_home)
_init_agent_db_schema(agent_home / "data", agent_name=agent.name, tenant_id=agent.tenant_id)

for suffix in ("1", "2"):
    observability.record_trace_event(
        observability.TraceEvent(
            run_id=f"skill-seed-{{suffix}}",
            event_type="workflow_observation",
            payload={{"task_pattern": "{pattern}"}},
            user_id=agent.name,
            agent_name=agent.name,
        )
    )
"""
    _run_agent_side_script_no_output(stack, script)


def wait_for_pending_skill_proposal(
    stack: ReflectionManagedStack,
    *,
    pattern: str,
) -> dict[str, object]:
    return wait_for_condition(
        lambda: _pending_skill_proposal(stack.agent_state_db, pattern=pattern),
        timeout=10.0,
        interval=0.5,
        description="pending skill reflection proposal",
    )


def _seed_reflection_agent(
    *,
    llm_stub_base_url: str,
    node_id: str,
    auto_apply: bool,
    interval_seconds: float,
) -> tuple[int, str]:
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
        config_overrides={
            "reflection": {
                "enabled": True,
                "interval_seconds": interval_seconds,
                "auto_apply": {"allow_low_risk": auto_apply},
            }
        },
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


def _latest_reflection_report(agent_state_db: Path) -> dict[str, object] | None:
    if not agent_state_db.exists():
        return None
    import sqlite3

    with sqlite3.connect(agent_state_db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, scope, domain, created_at
            FROM reflection_reports
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
    return dict(row) if row is not None else None


def _memory_apply_state(
    agent_state_db: Path,
    *,
    proposal_id: str,
    memory_id: str,
) -> dict[str, object] | None:
    if not agent_state_db.exists():
        return None
    import sqlite3

    with sqlite3.connect(agent_state_db) as conn:
        conn.row_factory = sqlite3.Row
        proposal = conn.execute(
            """
            SELECT id, applied_at
            FROM reflection_proposals
            WHERE id = :proposal_id
            """,
            {"proposal_id": proposal_id},
        ).fetchone()
        memory_row = conn.execute(
            """
            SELECT expires_at
            FROM memory_items
            WHERE id = :memory_id
            """,
            {"memory_id": memory_id},
        ).fetchone()
    if proposal is None or memory_row is None or proposal["applied_at"] is None:
        return None
    expires_at = str(memory_row["expires_at"]) if memory_row["expires_at"] is not None else None
    if expires_at is None:
        return None
    is_stale = datetime.fromisoformat(expires_at) <= datetime.now(UTC)
    if not is_stale:
        return None
    return {"proposal_status": "applied", "memory_status": "stale"}


def _pending_skill_proposal(agent_state_db: Path, *, pattern: str) -> dict[str, object] | None:
    if not agent_state_db.exists():
        return None
    import sqlite3

    with sqlite3.connect(agent_state_db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT domain, payload_json, applied_at
            FROM reflection_proposals
            WHERE domain = 'skill'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None or row["applied_at"] is not None:
        return None
    payload = json.loads(str(row["payload_json"]))
    draft = str(payload.get("suggested_draft") or "")
    if pattern not in draft:
        return None
    return {"domain": "skill", "status": "pending"}


def _run_agent_side_script(stack: ReflectionManagedStack, script: str) -> dict[str, str]:
    env = {
        **stack.common_env,
        "FLEETENT_AGENT_SUPPORT_MODEL": "sk-e2e-stub",
    }
    result = run_command(
        [sys.executable, "-c", script],
        env=env,
        cwd=repo_root(),
    )
    if result.returncode != 0:
        raise AssertionError(
            f"agent-side helper script failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return json.loads(result.stdout)


def _run_agent_side_script_no_output(stack: ReflectionManagedStack, script: str) -> None:
    env = {
        **stack.common_env,
        "FLEETENT_AGENT_SUPPORT_MODEL": "sk-e2e-stub",
    }
    result = run_command(
        [sys.executable, "-c", script],
        env=env,
        cwd=repo_root(),
    )
    if result.returncode != 0:
        raise AssertionError(
            f"agent-side helper script failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def _agent_tui_token(agent_home: Path) -> str:
    env_path = agent_home / ".env"
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("FLEETENT_TUI_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise AssertionError(f"FLEETENT_TUI_TOKEN not found in {env_path}")


def _restore_env(previous_env: dict[str, str | None]) -> None:
    for key, value in previous_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


_ENV_KEYS = ("DATABASE_URL", "FLEETENT_HOME", "FLEETENT_SECRET_KEY")
