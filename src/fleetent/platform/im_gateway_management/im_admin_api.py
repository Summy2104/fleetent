"""FastAPI router for /admin/im — IM connector registry + channel allowlist.

Read endpoints return masked credentials. enable/disable drive the connector manager
through injectable start/stop seams (the manager is async + lives in the app lifespan,
so the seams let this router and its tests stay synchronous). Never imports the agent
loop. Auth: admin-only (connector config carries credentials).
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from fleetent import auth, user_store
from fleetent.platform.im_gateway_management import (
    im_channel_allowlist,
    im_connector_config,
    im_connector_store,
)

router = APIRouter(prefix="/admin/im")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}


# --- injectable seams (connector manager lives in the async app lifespan) -----


def start_connector(platform: str) -> None:
    """Ask the running connector manager to start a platform (wired in server lifespan)."""
    return None


def stop_connector(platform: str) -> None:
    """Ask the running connector manager to stop a platform (wired in server lifespan)."""
    return None


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


def _require_admin(authorization: str | None) -> user_store.User:
    user = _session_user(authorization)
    if not auth.has_role(user, _ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="admin required")
    return user


# --- request bodies -----------------------------------------------------------


class ConnectorPatch(BaseModel):
    config: dict[str, str] | None = None
    allowlist_enforced: bool | None = None


class AllowlistBody(BaseModel):
    platform: str
    scope_type: str  # "channel" | "workspace"
    scope_id: str
    note: str | None = None


# --- connectors ---------------------------------------------------------------


def _masked_view(row: dict[str, Any]) -> dict[str, Any]:
    view = dict(row)
    view["config"] = im_connector_config.resolve_masked(row["platform"])
    return view


@router.get("/connectors")
def list_connectors(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _require_admin(authorization)
    return [_masked_view(row) for row in im_connector_store.list_connectors()]


@router.get("/connectors/{platform}")
def get_connector(platform: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _require_admin(authorization)
    row = im_connector_store.get_connector(platform)
    if row is None:
        raise HTTPException(status_code=404, detail="connector not found")
    return _masked_view(row)


@router.patch("/connectors/{platform}")
def patch_connector(
    platform: str, body: ConnectorPatch, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _require_admin(authorization)
    if im_connector_store.get_connector(platform) is None:
        raise HTTPException(status_code=404, detail="connector not found")
    if body.config is not None:
        im_connector_config.set_config(platform, body.config)
    if body.allowlist_enforced is not None:
        im_connector_store.set_allowlist_enforced(platform, body.allowlist_enforced)
    return _masked_view(im_connector_store.get_connector(platform))  # type: ignore[arg-type]


@router.post("/connectors/{platform}/enable")
def enable_connector(platform: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _require_admin(authorization)
    im_connector_store.set_enabled(platform, True)
    start_connector(platform)
    return {"platform": platform, "enabled": True}


@router.post("/connectors/{platform}/disable")
def disable_connector(platform: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _require_admin(authorization)
    im_connector_store.set_enabled(platform, False)
    stop_connector(platform)
    return {"platform": platform, "enabled": False}


# --- channel allowlist --------------------------------------------------------


@router.get("/allowlist")
def list_allowlist(
    platform: str | None = None, authorization: str | None = Header(None)
) -> list[dict[str, Any]]:
    _require_admin(authorization)
    return im_channel_allowlist.list_entries(platform)


@router.post("/allowlist", status_code=201)
def add_allowlist(body: AllowlistBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    _require_admin(authorization)
    try:
        im_channel_allowlist.add_entry(body.platform, body.scope_type, body.scope_id, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"platform": body.platform, "scope_id": body.scope_id, "added": True}


@router.delete("/allowlist/{entry_id}")
def delete_allowlist(entry_id: int, authorization: str | None = Header(None)) -> dict[str, Any]:
    _require_admin(authorization)
    im_channel_allowlist.remove_entry(entry_id)
    return {"id": entry_id, "removed": True}
