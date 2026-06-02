"""FastAPI router for /admin/agents version + binding management.

Adds the version-listing/activation and the four user/channel binding endpoints on
top of the agent management console, reusing the same Session auth + role guards
(viewer reads, admin writes). Agent rows and bindings come from agent_store; schema
lifecycle is owned by Alembic. This module never imports the agent loop.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from fleetent import agent_store, auth, user_store

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
