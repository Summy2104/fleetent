"""Admin endpoints to start/stop agent runtime processes (control plane).

`POST /admin/agents/<name>/start` materializes the agent home (if needed) and spawns
`fleetent agent run <name>`; `/stop` terminates the tracked process; the status endpoint
reports only tracked-running vs not (no deep health). Reuses the Session auth + admin
role guard pattern of the other admin routers (see ``platform-agent-lifecycle``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from fleetent import agent_store, auth, user_store
from fleetent.platform.agent_lifecycle import controller, materialize

router = APIRouter(prefix="/admin/agents", tags=["agent-lifecycle"])

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}

# Process control is in-memory and scoped to this platform process lifetime (no
# persistence, no supervision) — a single controller for the app.
_controller = controller.AgentController()


def _require_admin(authorization: str | None) -> user_store.User:
    if not authorization or not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="not authenticated")
    user_id = auth.validate_session(authorization.split(" ", 1)[1], IDLE_TIMEOUT_SECONDS)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user = user_store.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid session")
    if not auth.has_role(user, _ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="admin required")
    return user


def _materialize_if_needed(agent: agent_store.Agent) -> None:
    home = materialize.home_dir(agent.name)
    if not (home / "agent.yaml").exists():
        materialize.write_home(materialize.agent_file_from_store(agent))


@router.post("/{name}/start")
def start_agent(name: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin(authorization)
    agent = agent_store.get_by_name(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"agent {name!r} not found")
    _materialize_if_needed(agent)
    pid = _controller.start(name)
    return {"status": "running", "pid": pid}


@router.post("/{name}/stop")
def stop_agent(name: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin(authorization)
    stopped = _controller.stop(name)
    return {"status": "stopped" if stopped else "not-running"}


@router.get("/{name}/runtime-status")
def runtime_status(name: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin(authorization)
    return {"running": _controller.is_running(name)}
