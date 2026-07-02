"""FastAPI router for /admin/skills/git -- external git source sync control.

Three endpoints: ``POST /webhook`` (HMAC-gated push hook that triggers an inbound sync),
``POST /sync`` (admin manual trigger), ``GET /status`` (sync state; credential env-names only,
never secret values). Auth mirrors backflow_api (``Authorization: Session <token>``). The
webhook is HMAC-only (git platforms have no session) and REQUIRES a configured secret -- the
payload is never trusted, it only triggers a fetch (content is taken from fetch, not the body).
"""

from __future__ import annotations

import threading
from typing import Any

import anyio
from fastapi import APIRouter, Header, HTTPException, Request

from fleetent import auth, user_store
from fleetent.platform.skill_management import git_source_store, pool_sync
from fleetent.webhook_router import verify_signature

router = APIRouter(prefix="/admin/skills/git")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin"}
_sync_lock = threading.Lock()


def _session_user(authorization: str | None) -> user_store.User:
    if not authorization or not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="not authenticated")
    token = authorization.split(" ", 1)[1]
    user_id = auth.validate_session(token, IDLE_TIMEOUT_SECONDS)
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


def _secret(config: dict[str, Any] | None) -> str | None:
    if config is None:
        return None
    env = config.get("webhook_secret_env")
    return pool_sync._secret(env) if env else None


def webhook_decision(
    config: dict[str, Any] | None, secret: str | None, body: bytes, signature: str | None
) -> int:
    """Return the HTTP status for a webhook attempt (pure). 200 = accept.

    404 when the external source is not configured/enabled; 403 when no webhook secret is
    configured (a webhook MUST be authenticated -- verify_signature pass-throughs on a None
    secret); 401 on bad/missing signature; 200 when the HMAC verifies.
    """
    if config is None or not config.get("enabled"):
        return 404
    if not secret:
        return 403
    if not verify_signature(secret, body, signature):
        return 401
    return 200


def _status_payload(config: dict[str, Any] | None) -> dict[str, Any]:
    """Sync status + config for the UI: config fields + credential env-names only."""
    if config is None:
        return {"enabled": False}
    return {
        "enabled": bool(config.get("enabled")),
        "provider": config.get("provider"),
        "remote_url": config.get("remote_url"),
        "branch": config.get("branch"),
        "sync_interval_seconds": config.get("sync_interval_seconds"),
        "last_synced_commit": config.get("last_synced_commit"),
        "last_sync_at": config.get("last_sync_at"),
        "last_sync_error": config.get("last_sync_error"),
        "username_env": config.get("username_env"),
        "token_env": config.get("token_env"),
        "webhook_secret_env": config.get("webhook_secret_env"),
    }


@router.post("/webhook")
async def webhook(
    request: Request, x_hub_signature_256: str | None = Header(default=None)
) -> dict[str, Any]:
    """HMAC-gated push hook: verify then trigger an inbound sync (payload is not trusted)."""
    config = git_source_store.get_config()
    secret = _secret(config)
    body = await request.body()
    status_code = webhook_decision(config, secret, body, x_hub_signature_256)
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail="webhook rejected")
    if not _sync_lock.acquire(blocking=False):
        return {"accepted": True, "running": True}
    try:
        result: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: pool_sync.sync_external_git(trigger="webhook")
        )
    finally:
        _sync_lock.release()
    return {"accepted": True, **result}


@router.post("/sync")
async def manual_sync(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Admin manual trigger of an inbound sync."""
    _require_admin(authorization)
    result: dict[str, Any] = await anyio.to_thread.run_sync(
        lambda: pool_sync.sync_external_git(trigger="manual")
    )
    return result


@router.get("/status")
def get_status(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Return sync status + config (credential env-names only, never secret values)."""
    _session_user(authorization)  # viewer+ may read
    return _status_payload(git_source_store.get_config())
