"""FastAPI router for /admin user, API-key, IM-user, and audit management.

Authentication uses a login session token in the Authorization header:
``Authorization: Session <token>``. Reads allow viewer+admin; writes require admin.
This router does not import the agent loop, so it is testable in isolation.
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from fleetent import auth, im_user_store, user_store
from fleetent.governance import audit_log, blocklist
from fleetent.platform.user_management import api_key_store

router = APIRouter(prefix="/admin")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}
_UI_PATH = Path(__file__).parents[2] / "static" / "admin.html"


def _session_user(authorization: str | None, allow_must_reset: bool = False) -> user_store.User:
    """Resolve the login session to a user. Enforces the must-reset gate by default."""
    if not authorization or not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="not authenticated")
    token = authorization.split(" ", 1)[1]
    user_id = auth.validate_session(token, IDLE_TIMEOUT_SECONDS)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user = user_store.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid session")
    if user.must_reset and not allow_must_reset:
        raise HTTPException(status_code=403, detail="password reset required")
    return user


def _current_user(authorization: str | None) -> user_store.User:
    user = _session_user(authorization)
    if not auth.has_role(user, {"viewer", *_ADMIN_ROLES}):
        raise HTTPException(status_code=403, detail="forbidden")
    return user


def _require_admin(authorization: str | None) -> user_store.User:
    user = _current_user(authorization)
    if not auth.has_role(user, _ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="admin required")
    return user


def _enforce_2fa(user: user_store.User, code: str | None) -> None:
    """Gate a high-risk action: if the actor has 2FA enabled, a valid TOTP is required.

    Raises 403 before any business change when the code is missing or wrong, so
    delete/block/role/key-revoke do not take effect without a passing second factor.
    """
    if not user.totp_secret:
        return  # no second factor configured for this actor
    if not code or not auth.verify_user_2fa(user.id, code):
        raise HTTPException(status_code=403, detail="2FA verification required")


class LoginBody(BaseModel):
    email: str
    password: str


class ChangePasswordBody(BaseModel):
    new_password: str


@router.get("/ui", response_class=HTMLResponse)
def admin_ui() -> str:
    """Serve the self-contained admin console (vanilla JS, calls the JSON API)."""
    return _UI_PATH.read_text(encoding="utf-8")


def _resolve_login_user(identifier: str) -> user_store.User | None:
    """Resolve the login identifier to a user.

    Web users authenticate by email. The built-in admin is seeded with no email, so the
    login form's "Username" field also resolves it by its fixed built-in name.
    """
    user = user_store.get_by_email(identifier)
    if user is not None:
        return user
    if identifier == auth.BUILTIN_ADMIN_NAME:
        builtin = user_store.get_builtin_admin()
        if builtin is not None and builtin.name == identifier:
            return builtin
    return None


@router.post("/login")
def login(body: LoginBody) -> dict[str, Any]:
    user = _resolve_login_user(body.email)
    if user is None or not auth.verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    if user.status != "active":
        raise HTTPException(status_code=403, detail=f"account {user.status}")
    token = auth.create_session(user.id)
    return {"token": token, "role": user.role, "must_reset": bool(user.must_reset)}


@router.post("/logout")
def logout(authorization: str | None = Header(None)) -> dict[str, str]:
    if authorization and authorization.startswith("Session "):
        auth.logout(authorization.split(" ", 1)[1])
    return {"status": "logged_out"}


@router.get("/me")
def me(authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _session_user(authorization, allow_must_reset=True)
    return {"id": user.id, "email": user.email, "role": user.role, "must_reset": user.must_reset}


@router.post("/change-password")
def change_password(
    body: ChangePasswordBody, authorization: str | None = Header(None)
) -> dict[str, str]:
    user = _session_user(authorization, allow_must_reset=True)
    user_store.set_password(user.id, auth.hash_password(body.new_password), must_reset=False)
    return {"status": "password_changed"}


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
def delete_user(
    user_id: str,
    authorization: str | None = Header(None),
    x_2fa_code: str | None = Header(None, alias="X-2FA-Code"),
) -> None:
    admin = _require_admin(authorization)
    _enforce_2fa(admin, x_2fa_code)
    try:
        user_store.delete_user(user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    audit_log.write_audit(admin.id, "delete_user", target_type="user", target_id=user_id)


@router.patch("/users/{user_id}/role")
def set_role(
    user_id: str,
    body: RoleBody,
    authorization: str | None = Header(None),
    x_2fa_code: str | None = Header(None, alias="X-2FA-Code"),
) -> dict[str, Any]:
    admin = _require_admin(authorization)
    _enforce_2fa(admin, x_2fa_code)
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
    user_id: str,
    body: ReasonBody,
    authorization: str | None = Header(None),
    x_2fa_code: str | None = Header(None, alias="X-2FA-Code"),
) -> dict[str, str]:
    admin = _require_admin(authorization)
    _enforce_2fa(admin, x_2fa_code)
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


@router.post("/users/{user_id}/password")
def reset_user_password(
    user_id: str,
    body: ChangePasswordBody,
    authorization: str | None = Header(None),
    x_2fa_code: str | None = Header(None, alias="X-2FA-Code"),
) -> dict[str, str]:
    """Admin-set a new password for another user, forcing a reset on their next login."""
    admin = _require_admin(authorization)
    _enforce_2fa(admin, x_2fa_code)
    if user_store.get_by_id(user_id) is None:
        raise HTTPException(status_code=404, detail="not found")
    user_store.set_password(user_id, auth.hash_password(body.new_password), must_reset=True)
    audit_log.write_audit(admin.id, "reset_password", target_type="user", target_id=user_id)
    return {"status": "password_reset"}


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
def revoke_key(
    key_id: int,
    authorization: str | None = Header(None),
    x_2fa_code: str | None = Header(None, alias="X-2FA-Code"),
) -> None:
    admin = _require_admin(authorization)
    _enforce_2fa(admin, x_2fa_code)
    api_key_store.revoke_key(key_id)
    audit_log.write_audit(admin.id, "revoke_key", target_type="key", target_id=str(key_id))


@router.get("/im-users")
def list_im_users(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return im_user_store.list_all()


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


class BindImBody(BaseModel):
    user_id: str


@router.post("/im-users/{im_user_id}/bind")
def bind_im_user(
    im_user_id: int, body: BindImBody, authorization: str | None = Header(None)
) -> dict[str, str]:
    """Rebind an IM identity to an existing internal user (many-to-one)."""
    admin = _require_admin(authorization)
    try:
        im_user_store.rebind_im_identity(im_user_id, body.user_id, actor=admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "bound"}


@router.get("/audit")
def search_audit(
    action: str | None = None,
    actor: str | None = None,
    target_id: str | None = None,
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    _current_user(authorization)
    return audit_log.search_audit(action=action, actor=actor, target_id=target_id)
