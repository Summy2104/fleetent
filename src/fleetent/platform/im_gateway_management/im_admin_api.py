"""FastAPI router for /admin/im — IM connector registry + channel allowlist.

Read endpoints return masked credentials. enable/disable drive the connector manager
through injectable start/stop seams (the manager is async + lives in the app lifespan,
so the seams let this router and its tests stay synchronous). Never imports the agent
loop. Auth: admin-only (connector config carries credentials).
"""

from typing import Any, Literal

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


def start_connector(owner_id: str, platform: str) -> None:
    """Ask the running connector manager to start an owner's platform (wired in lifespan)."""
    return None


def stop_connector(owner_id: str, platform: str) -> None:
    """Ask the running connector manager to stop an owner's platform (wired in lifespan)."""
    return None


def _default_owner() -> str:
    """Owner scope for write/read-by-platform endpoints: the built-in admin owner."""
    return user_store.admin_owner_id()


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


class CreateConnectorBody(BaseModel):
    platform: Literal["telegram", "slack", "whatsapp"]
    config: dict[str, str]
    owner_id: str | None = None


class AllowlistBody(BaseModel):
    platform: str
    scope_type: str  # "channel" | "workspace"
    scope_id: str
    note: str | None = None
    owner_id: str | None = None


# --- connectors ---------------------------------------------------------------


def _masked_view(row: dict[str, Any]) -> dict[str, Any]:
    view = dict(row)
    view["config"] = im_connector_config.resolve_masked(row["owner_id"], row["platform"])
    return view


@router.get("/connectors")
def list_connectors(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    """Admin scope: returns every owner's connectors, each annotated with its owner_id."""
    _require_admin(authorization)
    return [_masked_view(row) for row in im_connector_store.list_connectors()]


@router.post("/connectors", status_code=201)
def create_connector(
    body: CreateConnectorBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    """Create (or update) a connector from the admin console.

    Idempotent: the underlying upsert keys on UNIQUE(owner_id, platform), so posting an
    existing (owner, platform) updates its config rather than inserting a duplicate.
    """
    _require_admin(authorization)
    owner = body.owner_id or _default_owner()
    im_connector_config.set_config(owner, body.platform, body.config)
    return _masked_view(im_connector_store.get_connector(owner, body.platform))  # type: ignore[arg-type]


@router.get("/connectors/{platform}")
def get_connector(
    platform: str, owner_id: str | None = None, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _require_admin(authorization)
    owner = owner_id or _default_owner()
    row = im_connector_store.get_connector(owner, platform)
    if row is None:
        raise HTTPException(status_code=404, detail="connector not found")
    return _masked_view(row)


@router.patch("/connectors/{platform}")
def patch_connector(
    platform: str,
    body: ConnectorPatch,
    owner_id: str | None = None,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    _require_admin(authorization)
    owner = owner_id or _default_owner()
    if im_connector_store.get_connector(owner, platform) is None:
        raise HTTPException(status_code=404, detail="connector not found")
    if body.config is not None:
        im_connector_config.set_config(owner, platform, body.config)
    if body.allowlist_enforced is not None:
        im_connector_store.set_allowlist_enforced(owner, platform, body.allowlist_enforced)
    return _masked_view(im_connector_store.get_connector(owner, platform))  # type: ignore[arg-type]


@router.post("/connectors/{platform}/enable")
def enable_connector(
    platform: str, owner_id: str | None = None, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _require_admin(authorization)
    owner = owner_id or _default_owner()
    im_connector_store.set_enabled(owner, platform, True)
    start_connector(owner, platform)
    return {"owner_id": owner, "platform": platform, "enabled": True}


@router.post("/connectors/{platform}/disable")
def disable_connector(
    platform: str, owner_id: str | None = None, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _require_admin(authorization)
    owner = owner_id or _default_owner()
    im_connector_store.set_enabled(owner, platform, False)
    stop_connector(owner, platform)
    return {"owner_id": owner, "platform": platform, "enabled": False}


# --- channel allowlist --------------------------------------------------------


@router.get("/allowlist")
def list_allowlist(
    platform: str | None = None,
    owner_id: str | None = None,
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    """Admin scope: owner_id omitted lists across all owners; platform optionally filters."""
    _require_admin(authorization)
    return im_channel_allowlist.list_entries(owner_id, platform)


@router.post("/allowlist", status_code=201)
def add_allowlist(body: AllowlistBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    _require_admin(authorization)
    owner = body.owner_id or _default_owner()
    try:
        im_channel_allowlist.add_entry(
            owner, body.platform, body.scope_type, body.scope_id, body.note
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"owner_id": owner, "platform": body.platform, "scope_id": body.scope_id, "added": True}


@router.delete("/allowlist/{entry_id}")
def delete_allowlist(entry_id: int, authorization: str | None = Header(None)) -> dict[str, Any]:
    _require_admin(authorization)
    im_channel_allowlist.remove_entry(entry_id)
    return {"id": entry_id, "removed": True}
