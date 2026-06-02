"""FastAPI router for /admin/agents — the Agent management console (lifecycle face).

Layers the operational management face on top of the agent definition/binding store:
enable/disable, archive (soft delete) with binding protection + restore, clone,
the read-only template library, managed/adhoc provenance + drift, and the per-agent
observation view.

Agent CRUD/versioning and the binding tables come from agent_store; per-agent metric
aggregation comes from observability. Those are reached through injectable seams
(mockable in tests). Lifecycle status / provenance / drift are persisted in
agent_admin_store. Never imports the agent loop.

Auth: reads allow viewer+admin, writes require admin; archive needs X-Confirm.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from fleetent import agent_admin_store, agent_templates, audit_log, auth, user_store

router = APIRouter(prefix="/admin")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}


# --- injectable seams (agent_store / observability) ---------------------------


def get_agent_def(name: str) -> dict[str, Any] | None:
    """Resolve an agent's active definition (id/system_prompt/allowed_tools)."""
    return None


def create_agent_def(name: str, system_prompt: str, allowed_tools: list[str]) -> None:
    """Create a new agent definition (no bindings). Bridges agent_store.create_agent."""
    return None


def references_for(agent_name: str) -> dict[str, Any]:
    """Who references an agent (users/channels) — drives archive protection."""
    agent = get_agent_def(agent_name)
    if agent is None:
        return {"users": [], "channels": []}
    return agent_admin_store.references(int(agent["id"]))


def agent_observability_agg(agent_name: str, window: str) -> dict[str, Any]:
    """Per-agent aggregation (calls/tokens/cost/error-rate/latency/approvals). Placeholder."""
    return {
        "agent_name": agent_name,
        "window": window,
        "calls": 0,
        "tokens": 0,
        "error_rate": 0.0,
        "approval_pass_rate": None,
        "recent_sessions": [],
    }


# --- auth helpers -------------------------------------------------------------


def _session_user(authorization: str | None) -> user_store.User:
    if not authorization or not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="not authenticated")
    user_id = auth.validate_session(authorization.split(" ", 1)[1], IDLE_TIMEOUT_SECONDS)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user = user_store.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid session")
    return user


def _current_user(authorization: str | None) -> user_store.User:
    user = _session_user(authorization)
    if not auth.has_role(user, {"viewer", *_ADMIN_ROLES}):
        raise HTTPException(status_code=403, detail="forbidden")
    return user


def _require_admin(authorization: str | None) -> user_store.User:
    user = _session_user(authorization)
    if not auth.has_role(user, _ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="admin required")
    return user


def _require_confirm(x_confirm: str | None) -> None:
    if x_confirm != "true":
        raise HTTPException(status_code=428, detail="confirmation required for high-risk action")


class CloneBody(BaseModel):
    new_name: str


# --- templates (literal path before /{name}) ----------------------------------


@router.get("/agent-templates")
def list_templates(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return agent_templates.list_templates()


# --- list ---------------------------------------------------------------------


@router.get("/agents")
def list_agents(
    include_archived: bool = False, authorization: str | None = Header(None)
) -> list[dict[str, Any]]:
    _current_user(authorization)
    return agent_admin_store.list_states(include_archived=include_archived)


@router.get("/agents/{name}/observability")
def observability(
    name: str, window: str = "7d", authorization: str | None = Header(None)
) -> dict[str, Any]:
    _current_user(authorization)
    return agent_observability_agg(name, window)


# --- lifecycle ----------------------------------------------------------------


@router.post("/agents/{name}/enable")
def enable_agent(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent_admin_store.enable(name)
    audit_log.write_audit(user.id, "agent.enable", "agent", name)
    return {"agent": name, "status": "enabled"}


@router.post("/agents/{name}/disable")
def disable_agent(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent_admin_store.disable(name)
    audit_log.write_audit(user.id, "agent.disable", "agent", name)
    return {"agent": name, "status": "disabled"}


@router.post("/agents/{name}/archive")
def archive_agent(
    name: str,
    authorization: str | None = Header(None),
    x_confirm: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    refs = references_for(name)
    if refs["users"] or refs["channels"]:
        raise HTTPException(status_code=409, detail={"error": "agent still bound", **refs})
    _require_confirm(x_confirm)
    agent_admin_store.archive(name)
    audit_log.write_audit(user.id, "agent.archive", "agent", name)
    return {"agent": name, "status": "archived"}


@router.post("/agents/{name}/restore")
def restore_agent(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent_admin_store.restore(name)
    audit_log.write_audit(user.id, "agent.restore", "agent", name)
    return {"agent": name, "status": "enabled"}


# --- clone --------------------------------------------------------------------


@router.post("/agents/{name}/clone")
def clone_agent(
    name: str, body: CloneBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    src = get_agent_def(name)
    if src is None:
        raise HTTPException(status_code=404, detail="source agent not found")
    if get_agent_def(body.new_name) is not None:
        raise HTTPException(status_code=409, detail="target name already exists")
    create_agent_def(body.new_name, src["system_prompt"], src["allowed_tools"])
    # clone is a fresh adhoc agent with no bindings and default enabled status
    agent_admin_store.set_provenance(body.new_name, "adhoc")
    agent_admin_store.enable(body.new_name)
    audit_log.write_audit(user.id, "agent.clone", "agent", body.new_name, detail={"source": name})
    return {"agent": body.new_name, "cloned_from": name, "provenance": "adhoc"}
