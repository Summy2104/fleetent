"""FastAPI router for /admin user, API-key, IM-user, and audit management.

Authentication uses a login session token in the Authorization header:
``Authorization: Session <token>``. Reads allow viewer+admin; writes require admin.
This router does not import the agent loop, so it is testable in isolation.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from fleetent import (
    api_key_store,
    audit_log,
    auth,
    blocklist,
    im_user_store,
    user_store,
)

router = APIRouter(prefix="/admin")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}


def _current_user(authorization: str | None) -> user_store.User:
    if not authorization or not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="not authenticated")
    token = authorization.split(" ", 1)[1]
    user_id = auth.validate_session(token, IDLE_TIMEOUT_SECONDS)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user = user_store.get_by_id(user_id)
    if not auth.has_role(user, {"viewer", *_ADMIN_ROLES}):
        raise HTTPException(status_code=403, detail="forbidden")
    assert user is not None
    return user


def _require_admin(authorization: str | None) -> user_store.User:
    user = _current_user(authorization)
    if not auth.has_role(user, _ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="admin required")
    return user


class CreateUserBody(BaseModel):
    email: str
    name: str
    password: str | None = None
    role: str = "viewer"
    must_reset: bool = False


class RoleBody(BaseModel):
    role: str


class ReasonBody(BaseModel):
    reason: str = ""


class IssueKeyBody(BaseModel):
    scope: list[str] = ["*"]
    note: str | None = None
    expires_at: str | None = None


def _user_dict(u: user_store.User) -> dict[str, Any]:
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "status": u.status,
        "must_reset": u.must_reset,
    }


@router.get("/users")
def list_users(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return [_user_dict(u) for u in user_store.list_users()]


@router.post("/users", status_code=201)
def create_user(body: CreateUserBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    _require_admin(authorization)
    pw_hash = auth.hash_password(body.password) if body.password else None
    try:
        user = user_store.create_web_user(
            body.email,
            body.name,
            password_hash=pw_hash,
            must_reset=body.must_reset,
            role=body.role,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _user_dict(user)


@router.get("/users/{user_id}")
def get_user(user_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    user = user_store.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="not found")
    return _user_dict(user)


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: str, authorization: str | None = Header(None)) -> None:
    admin = _require_admin(authorization)
    try:
        user_store.delete_user(user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    audit_log.write_audit(admin.id, "delete_user", target_type="user", target_id=user_id)


@router.patch("/users/{user_id}/role")
def set_role(
    user_id: str, body: RoleBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    admin = _require_admin(authorization)
    try:
        user_store.set_role(user_id, body.role)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    audit_log.write_audit(
        admin.id, "set_role", target_type="user", target_id=user_id, detail={"role": body.role}
    )
    return _user_dict(user_store.get_by_id(user_id))  # type: ignore[arg-type]


@router.post("/users/{user_id}/block")
def block_user(
    user_id: str, body: ReasonBody, authorization: str | None = Header(None)
) -> dict[str, str]:
    admin = _require_admin(authorization)
    try:
        blocklist.block_user(user_id, reason=body.reason, actor=admin.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"status": "blocked"}


@router.post("/users/{user_id}/unblock")
def unblock_user(user_id: str, authorization: str | None = Header(None)) -> dict[str, str]:
    admin = _require_admin(authorization)
    blocklist.unblock_user(user_id, actor=admin.id)
    return {"status": "active"}


@router.get("/users/{user_id}/keys")
def list_keys(user_id: str, authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return api_key_store.list_keys(user_id)


@router.post("/users/{user_id}/keys", status_code=201)
def issue_key(
    user_id: str, body: IssueKeyBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    admin = _require_admin(authorization)
    plaintext, meta = api_key_store.issue_key(
        user_id, scope=body.scope, note=body.note, expires_at=body.expires_at
    )
    audit_log.write_audit(admin.id, "issue_key", target_type="user", target_id=user_id)
    return {"plaintext": plaintext, "key": meta}


@router.delete("/keys/{key_id}", status_code=204)
def revoke_key(key_id: int, authorization: str | None = Header(None)) -> None:
    admin = _require_admin(authorization)
    api_key_store.revoke_key(key_id)
    audit_log.write_audit(admin.id, "revoke_key", target_type="key", target_id=str(key_id))


@router.post("/im-users/{im_user_id}/block")
def block_im_user(
    im_user_id: int, body: ReasonBody, authorization: str | None = Header(None)
) -> dict[str, bool]:
    admin = _require_admin(authorization)
    im_user_store.block_im_user(im_user_id, reason=body.reason, actor=admin.id)
    return {"allowed": False}


@router.post("/im-users/{im_user_id}/restore")
def restore_im_user(
    im_user_id: int, body: ReasonBody, authorization: str | None = Header(None)
) -> dict[str, bool]:
    admin = _require_admin(authorization)
    im_user_store.restore_im_user(im_user_id, reason=body.reason, actor=admin.id)
    return {"allowed": True}


@router.get("/audit")
def search_audit(
    action: str | None = None,
    actor: str | None = None,
    target_id: str | None = None,
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    _current_user(authorization)
    return audit_log.search_audit(action=action, actor=actor, target_id=target_id)
