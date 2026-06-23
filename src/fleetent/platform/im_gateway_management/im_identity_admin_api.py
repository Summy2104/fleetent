"""FastAPI router for the user↔IM relationship workbench (`/admin/im-identities`).

Lists IM identity mappings joined with their bound internal user (name + email) and lets
admins create or delete a binding. Authentication uses a login session token in the
Authorization header (``Authorization: Session <token>``); reads allow viewer+admin, writes
require admin. This router does not import the agent loop, so it is testable in isolation.

It coexists with the IM-user controls under ``/admin/im-users`` in user_admin_api (block /
restore / rebind / edit); this is the focused mapping-management surface.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from fleetent import auth, user_store
from fleetent.platform import im_gateway_management as im

router = APIRouter(prefix="/admin/im-identities")

_ADMIN_ROLES = {"admin", "built_in_admin"}
_VIEWER_ROLES = {"viewer", *_ADMIN_ROLES}
_IDLE_TIMEOUT_SECONDS = 1800


def _session_user(authorization: str | None) -> user_store.User:
    if not authorization or not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="not authenticated")
    token = authorization.split(" ", 1)[1]
    user_id = auth.validate_session(token, _IDLE_TIMEOUT_SECONDS)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user = user_store.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid session")
    return user


def _current_user(authorization: str | None) -> user_store.User:
    user = _session_user(authorization)
    if not auth.has_role(user, _VIEWER_ROLES):
        raise HTTPException(status_code=403, detail="forbidden")
    return user


def _require_admin(authorization: str | None) -> user_store.User:
    user = _current_user(authorization)
    if not auth.has_role(user, _ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="admin required")
    return user


class CreateMappingBody(BaseModel):
    platform: str
    platform_user_id: str
    user_id: str


@router.get("")
def list_im_mappings(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    """List every IM identity mapping with the bound internal user's name and email."""
    _current_user(authorization)
    return im.list_mappings()


@router.post("", status_code=201)
def create_im_mapping(
    body: CreateMappingBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    """Bind an external IM identity to an existing internal user."""
    admin = _require_admin(authorization)
    platform = body.platform.strip()
    platform_user_id = body.platform_user_id.strip()
    if not platform or not platform_user_id:
        raise HTTPException(status_code=422, detail="platform and platform_user_id are required")
    try:
        return im.create_mapping(platform, platform_user_id, body.user_id, actor=admin.id)
    except ValueError as exc:
        # "already exists" is a uniqueness conflict; anything else is a missing target user.
        status = 409 if "already exists" in str(exc) else 404
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.delete("/{im_user_id}", status_code=204)
def delete_im_mapping(im_user_id: int, authorization: str | None = Header(None)) -> None:
    """Delete an IM identity mapping. The bound internal user is left untouched."""
    admin = _require_admin(authorization)
    try:
        im.delete_im_identity(im_user_id, actor=admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
