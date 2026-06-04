"""FastAPI router for /admin/agents version + binding management.

Adds the version-listing/activation and the four user/channel binding endpoints on
top of the agent management console, reusing the same Session auth + role guards
(viewer reads, admin writes). Agent rows and bindings come from agent_store; schema
lifecycle is owned by Alembic. This module never imports the agent loop.
"""

from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException

from fleetent import agent_store, auth, config, user_store
from fleetent.governance import audit_log
from fleetent.platform.skill_management import skill_admin_store
from fleetent.skills import registry as skill_registry

router = APIRouter(prefix="/admin")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}


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


def _require_agent(name: str) -> agent_store.Agent:
    agent = agent_store.get_by_name(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"agent {name!r} not found")
    return agent


def _known_mcp_server_ids() -> set[str]:
    """Seam: the set of MCP server ids an agent may bind to (from config)."""
    return {s.id for s in config.load_mcp_server_settings()}


@router.get("/agents/{name}/versions")
def list_versions(name: str, authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    _require_agent(name)
    return [
        {
            "id": v.id,
            "version": v.version,
            "is_active": v.is_active,
            "created_at": v.created_at,
        }
        for v in agent_store.list_versions(name)
    ]


@router.post("/agents/{name}/versions/{version}/activate")
def activate_version(
    name: str, version: int, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _require_admin(authorization)
    _require_agent(name)
    try:
        agent_store.activate_version(name, version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"name": name, "active_version": version}


@router.post("/agents/{name}/bindings/users/{user_id}")
def bind_user(name: str, user_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _require_admin(authorization)
    agent = _require_agent(name)
    agent_store.assign_user(user_id, agent.id)
    return {"agent": name, "user_id": user_id, "bound": True}


@router.delete("/agents/{name}/bindings/users/{user_id}")
def unbind_user(
    name: str, user_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _require_admin(authorization)
    agent = _require_agent(name)
    agent_store.unassign_user(user_id, agent.id)
    return {"agent": name, "user_id": user_id, "bound": False}


@router.post("/agents/{name}/bindings/channels/{platform}/{channel_id}")
def bind_channel(
    name: str,
    platform: str,
    channel_id: str,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    _require_admin(authorization)
    agent = _require_agent(name)
    agent_store.assign_channel(platform, channel_id, agent.id)
    return {"agent": name, "platform": platform, "channel_id": channel_id, "bound": True}


@router.delete("/agents/{name}/bindings/channels/{platform}/{channel_id}")
def unbind_channel(
    name: str,
    platform: str,
    channel_id: str,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    _require_admin(authorization)
    _require_agent(name)
    agent_store.unassign_channel(platform, channel_id)
    return {"agent": name, "platform": platform, "channel_id": channel_id, "bound": False}


# --- aggregate bindings read --------------------------------------------------


@router.get("/agents/{name}/bindings")
def get_bindings(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    agent = _require_agent(name)
    return {
        "users": agent_store.list_users_for_agent(agent.id),
        "channels": agent_store.list_channels_for_agent(agent.id),
        "mcp_servers": agent_store.list_mcp_servers_for_agent(agent.id),
    }


# --- agent-side skill bindings ------------------------------------------------


@router.get("/agents/{name}/skills")
def list_agent_skills(name: str, authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    _require_agent(name)
    enabled = skill_admin_store.enabled_skill_names(name)
    bound = {
        str(r["skill_name"]): bool(r["enabled"])
        for r in skill_admin_store.list_skills_for_agent(name)
    }
    names = {s["name"] for s in skill_registry.list_skills()} | set(bound)
    return [{"skill_name": n, "enabled": bound.get(n, n in enabled)} for n in sorted(names)]


@router.put("/agents/{name}/skills/{skill_name}")
def set_agent_skill(
    name: str,
    skill_name: str,
    enabled: bool = Body(..., embed=True),
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    _require_agent(name)
    skill_admin_store.set_binding(name, skill_name, enabled, updated_by=user.id)
    audit_log.write_audit(
        user.id,
        "agent.skill.set",
        target_type="agent",
        target_id=name,
        detail={"skill_name": skill_name, "enabled": enabled},
    )
    return {"agent": name, "skill_name": skill_name, "enabled": enabled}


# --- agent MCP bindings -------------------------------------------------------


@router.post("/agents/{name}/bindings/mcp/{server_id}")
def bind_mcp(name: str, server_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent = _require_agent(name)
    if server_id not in _known_mcp_server_ids():
        raise HTTPException(status_code=404, detail=f"mcp server {server_id!r} not found")
    agent_store.bind_mcp_server(agent.id, server_id, created_by=user.id)
    audit_log.write_audit(
        user.id,
        "agent.mcp.bind",
        target_type="agent",
        target_id=name,
        detail={"server_id": server_id},
    )
    return {"agent": name, "server_id": server_id, "bound": True}


@router.delete("/agents/{name}/bindings/mcp/{server_id}")
def unbind_mcp(
    name: str, server_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    agent = _require_agent(name)
    agent_store.unbind_mcp_server(agent.id, server_id)
    audit_log.write_audit(
        user.id,
        "agent.mcp.unbind",
        target_type="agent",
        target_id=name,
        detail={"server_id": server_id},
    )
    return {"agent": name, "server_id": server_id, "bound": False}
