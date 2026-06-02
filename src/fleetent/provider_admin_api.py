"""FastAPI router for /admin/providers — the model_provider management face.

Owns the management behaviour only: provider CRUD (api_key masked on output),
task_type → provider route orchestration (list order = fallback priority),
connectivity test, fallback-chain preview, health-probe view, pricing table, and
per-provider observation. The runtime routing/fallback/client-instantiation and
cost collection live in the model-router / observability domains and are reached
through injectable seams (mockable in tests). This router never imports the agent
loop, so it is testable in isolation.

Auth mirrors user_admin_api: reads allow viewer+admin, writes require admin.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from fleetent import audit_log, auth, provider_admin_store, user_store

router = APIRouter(prefix="/admin/providers")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}
_DEFAULT_TASK_TYPE = "default"


# --- injectable seams (model-router / observability follow-ups) ---------------


def router_connectivity_test(provider: dict[str, Any]) -> dict[str, Any]:
    """Probe a provider endpoint. Owned by model-router (follow-up placeholder).

    Returns ``{"reachable", "latency_ms", "model"}``. Tests monkeypatch this.
    The probe must not record observability usage/cost.
    """
    return {
        "reachable": False,
        "latency_ms": None,
        "model": provider.get("model"),
        "error": "connectivity probe not wired (model-router follow-up)",
    }


def router_health_probe() -> dict[str, Any]:
    """Health-probe cache (which providers are temporarily down). Placeholder."""
    return {}


def provider_observability(provider_id: str) -> dict[str, Any]:
    """Per-provider·model usage metrics. Owned by observability (placeholder)."""
    return {
        "provider_id": provider_id,
        "calls": 0,
        "tokens": 0,
        "error_rate": 0.0,
        "task_types": [],
        "agents": [],
    }


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


# --- masking serializer -------------------------------------------------------


def _serialize(provider: dict[str, Any]) -> dict[str, Any]:
    """Copy a provider row for output, masking the api_key (never returned plaintext)."""
    out = dict(provider)
    key = out.get("api_key")
    out["api_key"] = "****" if key else None
    out["api_key_set"] = bool(key)
    return out


def _cost_label(price: float | None) -> str | float:
    return "未配置" if price is None else price


# --- request bodies -----------------------------------------------------------


class ProviderBody(BaseModel):
    id: str
    base_url: str
    model: str
    api_key: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    extra_params: dict[str, Any] | None = None


class ProviderEditBody(BaseModel):
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    extra_params: dict[str, Any] | None = None


class RouteOrderBody(BaseModel):
    provider_ids: list[str]


class PricingBody(BaseModel):
    input_price_per_1k: float | None = None
    output_price_per_1k: float | None = None


# --- routing views (declared before /{id} to avoid path capture) -------------


@router.get("/routes")
def list_routes(authorization: str | None = Header(None)) -> dict[str, list[str]]:
    _current_user(authorization)
    return {
        tt: provider_admin_store.get_route_providers(tt)
        for tt in provider_admin_store.list_route_task_types()
    }


@router.put("/routes/{task_type}")
def set_route(
    task_type: str, body: RouteOrderBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    provider_admin_store.set_route_order(task_type, body.provider_ids)
    audit_log.write_audit(
        user.id,
        "provider.route_set",
        "task_type",
        task_type,
        detail={"order": body.provider_ids},
    )
    return {"task_type": task_type, "providers": body.provider_ids}


@router.get("/routes/{task_type}/preview")
def preview_route(task_type: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    chain = provider_admin_store.get_route_providers(task_type)
    if not chain:
        # model-router falls back to "default" at runtime when a task_type is unconfigured.
        return {"task_type": task_type, "chain": [], "falls_back_to": _DEFAULT_TASK_TYPE}
    return {"task_type": task_type, "chain": chain, "falls_back_to": None}


@router.get("/health")
def health(authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    return router_health_probe()


# --- provider list / CRUD -----------------------------------------------------


@router.get("")
def list_providers(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return [_serialize(p) for p in provider_admin_store.list_providers()]


@router.post("")
def add_provider(body: ProviderBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    if provider_admin_store.get_provider(body.id) is not None:
        raise HTTPException(status_code=409, detail="provider id already exists")
    provider_admin_store.add_provider(
        body.id,
        base_url=body.base_url,
        model=body.model,
        api_key=body.api_key,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
        extra_params=body.extra_params,
    )
    audit_log.write_audit(
        user.id,
        "provider.add",
        "provider",
        body.id,
        detail={"base_url": body.base_url, "model": body.model},
    )
    created = provider_admin_store.get_provider(body.id)
    if created is None:
        raise HTTPException(status_code=500, detail="provider not found after add")
    return _serialize(created)


@router.put("/{provider_id}")
def edit_provider(
    provider_id: str, body: ProviderEditBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if provider_admin_store.get_provider(provider_id) is None:
        raise HTTPException(status_code=404, detail="provider not found")
    provider_admin_store.edit_provider(provider_id, **body.model_dump(exclude_unset=True))
    audit_log.write_audit(user.id, "provider.edit", "provider", provider_id)
    edited = provider_admin_store.get_provider(provider_id)
    if edited is None:
        raise HTTPException(status_code=500, detail="provider not found after edit")
    return _serialize(edited)


@router.delete("/{provider_id}")
def delete_provider(provider_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    provider_admin_store.delete_provider(provider_id)
    audit_log.write_audit(user.id, "provider.delete", "provider", provider_id)
    return {"id": provider_id, "deleted": True}


# --- connectivity test --------------------------------------------------------


@router.post("/{provider_id}/connectivity-test")
def connectivity_test(provider_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    provider = provider_admin_store.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    result = router_connectivity_test(provider)
    audit_log.write_audit(
        user.id,
        "provider.connectivity_test",
        "provider",
        provider_id,
        detail={"reachable": result.get("reachable")},
    )
    return result


# --- pricing ------------------------------------------------------------------


@router.put("/{provider_id}/pricing")
def set_pricing(
    provider_id: str, body: PricingBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if provider_admin_store.get_provider(provider_id) is None:
        raise HTTPException(status_code=404, detail="provider not found")
    provider_admin_store.set_pricing(provider_id, body.input_price_per_1k, body.output_price_per_1k)
    audit_log.write_audit(user.id, "provider.pricing_set", "provider", provider_id)
    p = provider_admin_store.get_provider(provider_id)
    if p is None:
        raise HTTPException(status_code=500, detail="provider not found after pricing update")
    return {
        "id": provider_id,
        "input_price_per_1k": _cost_label(p["input_price_per_1k"]),
        "output_price_per_1k": _cost_label(p["output_price_per_1k"]),
    }


# --- observation --------------------------------------------------------------


@router.get("/{provider_id}/observability")
def observability(provider_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    provider = provider_admin_store.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    metrics = provider_observability(provider_id)
    metrics["input_price_per_1k"] = _cost_label(provider["input_price_per_1k"])
    metrics["output_price_per_1k"] = _cost_label(provider["output_price_per_1k"])
    return metrics
