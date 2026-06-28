"""FastAPI router for provider credentials on the split model registry."""

import re
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from fleetent import audit_log, auth, user_store
from fleetent.platform.model_provider_management import model_admin_store, provider_admin_store

router = APIRouter(prefix="/admin/providers")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin"}


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


def _derive_api_key_env(provider_id: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", provider_id).strip("_").upper()
    return f"FLEETENT_MODEL_{slug}_API_KEY"


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) < 12:
        return "****"
    return f"{key[:4]}…{key[-4:]}"


def _serialize(provider: dict[str, Any]) -> dict[str, Any]:
    out = dict(provider)
    key = out.get("api_key")
    out["api_key"] = _mask_key(key)
    out["api_key_set"] = bool(key)
    out["provider"] = out.get("vendor")
    out["model_count"] = len(model_admin_store.list_models(provider_id=str(provider["id"])))
    return out


class ProviderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None


class ProviderEditBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None


@router.get("")
def list_providers(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return [_serialize(provider) for provider in provider_admin_store.list_providers()]


@router.post("")
def add_provider(body: ProviderBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    if provider_admin_store.get_provider(body.id) is not None:
        raise HTTPException(status_code=409, detail="provider id already exists")
    api_key_env = body.api_key_env or (_derive_api_key_env(body.id) if body.api_key else None)
    provider_admin_store.add_provider(
        body.id,
        description=body.description,
        provider=body.provider,
        base_url=body.base_url,
        api_key=body.api_key,
        api_key_env=api_key_env,
    )
    audit_log.write_audit(user.id, "provider.add", "provider", body.id)
    created = provider_admin_store.get_provider(body.id)
    if created is None:
        raise HTTPException(status_code=500, detail="provider not found after add")
    return _serialize(created)


@router.put("/{provider_id}")
def edit_provider(
    provider_id: str,
    body: ProviderEditBody,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if provider_admin_store.get_provider(provider_id) is None:
        raise HTTPException(status_code=404, detail="provider not found")
    updates = body.model_dump(exclude_unset=True)
    if updates.get("api_key") and not updates.get("api_key_env"):
        updates["api_key_env"] = _derive_api_key_env(provider_id)
    provider_admin_store.edit_provider(provider_id, **updates)
    audit_log.write_audit(user.id, "provider.edit", "provider", provider_id)
    edited = provider_admin_store.get_provider(provider_id)
    if edited is None:
        raise HTTPException(status_code=500, detail="provider not found after edit")
    return _serialize(edited)


@router.delete("/{provider_id}")
def delete_provider(provider_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    models = [str(row["id"]) for row in model_admin_store.list_models(provider_id=provider_id)]
    if models:
        refs = model_admin_store.references_for_provider(provider_id)
        raise HTTPException(
            status_code=409,
            detail={
                "error": "provider still has models",
                "models": models,
                "agents": refs["agents"],
            },
        )
    provider_admin_store.delete_provider(provider_id)
    audit_log.write_audit(user.id, "provider.delete", "provider", provider_id)
    return {"id": provider_id, "deleted": True}


@router.get("/{provider_id}/references")
def provider_references(
    provider_id: str, authorization: str | None = Header(None)
) -> dict[str, list[str]]:
    _current_user(authorization)
    if provider_admin_store.get_provider(provider_id) is None:
        raise HTTPException(status_code=404, detail="provider not found")
    return model_admin_store.references_for_provider(provider_id)
