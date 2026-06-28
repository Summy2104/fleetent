"""FastAPI router for models on the split model registry."""

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, model_validator

from fleetent import audit_log, auth, user_store
from fleetent.platform.model_provider_management import model_admin_store, provider_admin_store
from fleetent.platform.model_provider_management.provider_connectivity import (
    test_provider_connectivity_sync,
)

router = APIRouter(prefix="/admin/models")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin"}
_ENDPOINT_PROTOCOLS = {"http_embedding", "http_rerank", "openai_image_generation"}


def router_connectivity_test(model: dict[str, Any], provider: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "base_url": model.get("base_url") or model.get("endpoint"),
        "model": model.get("model_name"),
        "api_key": provider.get("api_key"),
    }
    return test_provider_connectivity_sync(payload)


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


class ModelBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    provider_id: str
    protocol: str
    model_name: str
    base_url: str | None = None
    endpoint: str | None = None
    max_tokens: int | None = None
    input_price_per_1k: float | None = None
    output_price_per_1k: float | None = None
    params: dict[str, Any] | None = None
    extra_params: dict[str, Any] | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _validate_connection_fields(self) -> "ModelBody":
        if self.protocol in _ENDPOINT_PROTOCOLS:
            if not self.endpoint or self.base_url is not None:
                raise ValueError("endpoint protocol requires endpoint and forbids base_url")
        elif not self.base_url:
            raise ValueError("chat protocol requires base_url")
        return self


class ModelEditBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str | None = None
    protocol: str | None = None
    model_name: str | None = None
    base_url: str | None = None
    endpoint: str | None = None
    max_tokens: int | None = None
    input_price_per_1k: float | None = None
    output_price_per_1k: float | None = None
    params: dict[str, Any] | None = None
    extra_params: dict[str, Any] | None = None
    description: str | None = None


@router.get("")
def list_models(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return model_admin_store.list_models()


@router.post("")
def add_model(body: ModelBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    if provider_admin_store.get_provider(body.provider_id) is None:
        raise HTTPException(status_code=404, detail="provider not found")
    if model_admin_store.get_model(body.id) is not None:
        raise HTTPException(status_code=409, detail="model id already exists")
    model_admin_store.add_model(
        body.id,
        provider_id=body.provider_id,
        protocol=body.protocol,
        model_name=body.model_name,
        base_url=body.base_url,
        endpoint=body.endpoint,
        max_tokens=body.max_tokens,
        input_price_per_1k=body.input_price_per_1k,
        output_price_per_1k=body.output_price_per_1k,
        params=body.params,
        extra_params=body.extra_params,
        description=body.description,
    )
    audit_log.write_audit(user.id, "model.add", "model", body.id)
    created = model_admin_store.get_model(body.id)
    if created is None:
        raise HTTPException(status_code=500, detail="model not found after add")
    return created


@router.put("/{model_id}")
def edit_model(model_id: str, body: ModelEditBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    if model_admin_store.get_model(model_id) is None:
        raise HTTPException(status_code=404, detail="model not found")
    updates = body.model_dump(exclude_unset=True)
    if "provider_id" in updates and provider_admin_store.get_provider(str(updates["provider_id"])) is None:
        raise HTTPException(status_code=404, detail="provider not found")
    model_admin_store.edit_model(model_id, **updates)
    audit_log.write_audit(user.id, "model.edit", "model", model_id)
    edited = model_admin_store.get_model(model_id)
    if edited is None:
        raise HTTPException(status_code=500, detail="model not found after edit")
    return edited


@router.delete("/{model_id}")
def delete_model(model_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    if model_admin_store.get_model(model_id) is None:
        raise HTTPException(status_code=404, detail="model not found")
    refs = model_admin_store.references_for_model(model_id)
    if refs["agents"]:
        raise HTTPException(status_code=409, detail={"error": "model still referenced", **refs})
    model_admin_store.delete_model(model_id)
    audit_log.write_audit(user.id, "model.delete", "model", model_id)
    return {"id": model_id, "deleted": True}


@router.get("/{model_id}/references")
def model_references(model_id: str, authorization: str | None = Header(None)) -> dict[str, list[str]]:
    _current_user(authorization)
    if model_admin_store.get_model(model_id) is None:
        raise HTTPException(status_code=404, detail="model not found")
    return model_admin_store.references_for_model(model_id)


@router.post("/{model_id}/connectivity-test")
def connectivity_test(model_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    model = model_admin_store.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")
    provider = provider_admin_store.get_provider(str(model["provider_id"]))
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    result = router_connectivity_test(model, provider)
    audit_log.write_audit(
        user.id,
        "model.connectivity_test",
        "model",
        model_id,
        detail={"reachable": result.get("reachable")},
    )
    return result
