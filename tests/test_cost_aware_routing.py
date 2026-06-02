"""Tests for cost-aware routing (MR2)."""

import fleetent.model_router as mr
from fleetent.cost_aware_routing import (
    CostAction,
    CostAwareRoutingPolicy,
    resolve_base_route,
)
from fleetent.layered_budget import BudgetHeadroom
from fleetent.model_router import RouteConfig, RouteOverride


def _hr(ratio):
    return BudgetHeadroom(cost_remaining_ratio=ratio, tightest_scope="user")


# ── BudgetHeadroom is consumed, not defined here (D1) ────────────────────────


def test_budget_headroom_imported_from_ar18():
    import fleetent.cost_aware_routing as car
    import fleetent.layered_budget as lbud

    assert car.BudgetHeadroom is lbud.BudgetHeadroom  # consumed, not redefined


# ── policy.decide two tiers (D2) ─────────────────────────────────────────────


def test_decide_normal_when_disabled():
    pol = CostAwareRoutingPolicy(enabled=False, degrade_below=0.5, degrade_target="cheap")
    assert pol.decide(_hr(0.1)) is CostAction.normal


def test_decide_degrade_below_threshold():
    pol = CostAwareRoutingPolicy(enabled=True, degrade_below=0.2, degrade_target="cheap")
    assert pol.decide(_hr(0.1)) is CostAction.degrade


def test_decide_normal_above_threshold():
    pol = CostAwareRoutingPolicy(enabled=True, degrade_below=0.2, degrade_target="cheap")
    assert pol.decide(_hr(0.9)) is CostAction.normal


def test_decide_normal_when_headroom_none():
    pol = CostAwareRoutingPolicy(enabled=True, degrade_below=0.2, degrade_target="cheap")
    assert pol.decide(None) is CostAction.normal


def test_decide_normal_when_no_target_even_if_tight():
    # No explicit degrade_target → never silently degrade (quality cliff guard).
    pol = CostAwareRoutingPolicy(enabled=True, degrade_below=0.9, degrade_target=None)
    assert pol.decide(_hr(0.0)) is CostAction.normal


def test_from_settings_default_inert(monkeypatch):
    from fleetent.config import Settings

    pol = CostAwareRoutingPolicy.from_settings(Settings(anthropic_api_key="x"))
    assert pol.enabled is False and pol.degrade_target is None
    assert pol.decide(_hr(0.0)) is CostAction.normal  # whole chain inert by default


# ── resolve_base_route (D3) ──────────────────────────────────────────────────


_ROUTES = {
    "default": RouteConfig(base_url="u", model="big", api_key_env="K", max_tokens=100),
    "cheap": RouteConfig(base_url="u", model="small", api_key_env="K", max_tokens=100),
    "special": RouteConfig(base_url="u", model="special-m", api_key_env="K", max_tokens=100),
}


def test_resolve_normal_returns_task_route():
    pol = CostAwareRoutingPolicy(enabled=True, degrade_below=0.2, degrade_target="cheap")
    cfg = resolve_base_route(_ROUTES, "special", _hr(0.9), pol)  # ample → no degrade
    assert cfg.model == "special-m"


def test_resolve_degrade_uses_target():
    pol = CostAwareRoutingPolicy(enabled=True, degrade_below=0.2, degrade_target="cheap")
    cfg = resolve_base_route(_ROUTES, "special", _hr(0.05), pol)  # tight → degrade
    assert cfg.model == "small"


def test_resolve_unknown_target_falls_back_to_default():
    pol = CostAwareRoutingPolicy(enabled=True, degrade_below=0.2, degrade_target="ghost")
    cfg = resolve_base_route(_ROUTES, "special", _hr(0.05), pol)  # degrade, but ghost missing
    assert cfg.model == "big"  # default fallback, no raise


# ── model_router integration (D4) ────────────────────────────────────────────


def test_router_headroom_none_byte_identical(monkeypatch):
    monkeypatch.setattr(mr, "_load_routes", lambda: dict(_ROUTES))
    monkeypatch.setenv("K", "key")
    _, cfg_plain = mr.get_client_and_config("special")
    _, cfg_none = mr.get_client_and_config("special", headroom=None)
    assert cfg_plain == cfg_none  # None headroom == pre-MR2 path


def test_router_degrade_switches_route(monkeypatch):
    monkeypatch.setattr(mr, "_load_routes", lambda: dict(_ROUTES))
    monkeypatch.setenv("K", "key")
    pol = CostAwareRoutingPolicy(enabled=True, degrade_below=0.2, degrade_target="cheap")
    _, cfg = mr.get_client_and_config("special", headroom=_hr(0.05), policy=pol)
    assert cfg.model == "small"  # degraded
    _, cfg_ample = mr.get_client_and_config("special", headroom=_hr(0.9), policy=pol)
    assert cfg_ample.model == "special-m"  # ample → unchanged


def test_router_override_after_degrade(monkeypatch):
    monkeypatch.setattr(mr, "_load_routes", lambda: dict(_ROUTES))
    monkeypatch.setenv("K", "key")
    pol = CostAwareRoutingPolicy(enabled=True, degrade_below=0.2, degrade_target="cheap")
    # Degrade picks "cheap" (small), then override forces a specific model on top.
    _, cfg = mr.get_client_and_config(
        "special", RouteOverride(model="forced"), headroom=_hr(0.05), policy=pol
    )
    assert cfg.model == "forced"  # override wins (applied after degrade)


async def test_async_router_headroom_none_byte_identical(monkeypatch):
    monkeypatch.setattr(mr, "_load_routes", lambda: dict(_ROUTES))
    monkeypatch.setenv("K", "key")
    _, cfg_plain = mr.get_async_client_and_config("special")
    _, cfg_none = mr.get_async_client_and_config("special", headroom=None)
    assert cfg_plain == cfg_none
