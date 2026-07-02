"""FastAPI router for /admin/webhooks/sources (live-webhooks, managed).

Admin-only CRUD over managed webhook sources. The HMAC secret is write-only: it is accepted on
create, stored as ciphertext (via the store), and never echoed back in any response.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from fleetent import audit_log, auth, user_store
from fleetent.platform.webhook_management import webhook_source_store as store

router = APIRouter(prefix="/admin")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin"}


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


class WebhookSourceCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    agent_id: int | None = None
    message_template: str | None = None
    reply_target: str | None = None
    enabled: bool = True
    secret: str | None = None  # write-only; stored as ciphertext, never echoed


class WebhookSourceUpdateBody(BaseModel):
    """Update payload. ``id`` is immutable (path param) and thus absent here.

    The secret is governed by ``secret_action`` so an omitted secret cannot silently wipe an
    existing one: ``keep`` (default) leaves it, ``set`` overwrites with ``secret``, ``clear`` drops
    it. ``set`` without a ``secret`` value is a 400.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str
    agent_id: int | None = None
    message_template: str | None = None
    reply_target: str | None = None
    enabled: bool = True
    secret_action: Literal["keep", "set", "clear"] = "keep"
    secret: str | None = None  # write-only; required when secret_action == "set"


def _public_view(src: store.StoredWebhookSource) -> dict[str, object]:
    """Source projection for API responses: ``has_secret`` flag instead of the secret."""
    return {
        "id": src.id,
        "user_id": src.user_id,
        "agent_id": src.agent_id,
        "message_template": src.message_template,
        "reply_target": src.reply_target,
        "enabled": src.enabled,
        "has_secret": src.secret is not None,
    }


@router.get("/webhooks/sources")
def list_webhook_sources(authorization: str | None = Header(None)) -> list[dict[str, object]]:
    _require_admin(authorization)
    return [_public_view(s) for s in store.list_sources()]


@router.post("/webhooks/sources", status_code=201)
def create_webhook_source(
    body: WebhookSourceCreateBody, authorization: str | None = Header(None)
) -> dict[str, object]:
    user = _require_admin(authorization)
    store.put_source(
        id=body.id,
        user_id=body.user_id,
        agent_id=body.agent_id,
        message_template=body.message_template,
        reply_target=body.reply_target,
        enabled=body.enabled,
        secret=body.secret,
    )
    audit_log.write_audit(user.id, "webhook.create", "webhook_source", body.id)
    created = store.get_source(body.id)
    assert created is not None
    return _public_view(created)


@router.put("/webhooks/sources/{source_id}")
def update_webhook_source(
    source_id: str, body: WebhookSourceUpdateBody, authorization: str | None = Header(None)
) -> dict[str, object]:
    user = _require_admin(authorization)
    if store.get_source(source_id) is None:
        raise HTTPException(status_code=404, detail="webhook source not found")
    if body.secret_action == "set" and body.secret is None:
        raise HTTPException(status_code=400, detail="secret required when secret_action is 'set'")
    store.update_source(
        id=source_id,
        user_id=body.user_id,
        agent_id=body.agent_id,
        message_template=body.message_template,
        reply_target=body.reply_target,
        enabled=body.enabled,
        secret_action=body.secret_action,
        secret=body.secret,
    )
    audit_log.write_audit(user.id, "webhook.update", "webhook_source", source_id)
    updated = store.get_source(source_id)
    assert updated is not None
    return _public_view(updated)


@router.delete("/webhooks/sources/{source_id}", status_code=204)
def delete_webhook_source(source_id: str, authorization: str | None = Header(None)) -> None:
    user = _require_admin(authorization)
    store.delete_source(source_id)
    audit_log.write_audit(user.id, "webhook.delete", "webhook_source", source_id)
