"""Unit: @tool(risk_level=callable) is evaluated at call time (permission-gate D7)."""

from __future__ import annotations

import pytest

from fleetent.tools import registry


@pytest.fixture
def _clean_registry(monkeypatch):
    # Isolate the module-level registries so test tools don't leak.
    monkeypatch.setattr(registry, "_risk_levels", dict(registry._risk_levels))
    monkeypatch.setattr(registry, "_registry", dict(registry._registry))
    yield


def test_static_risk_level_still_resolves(_clean_registry):
    @registry.tool(risk_level="medium")
    def _static_tool() -> str:
        return "ok"

    assert registry.get_risk_level("_static_tool") == "medium"
    assert registry.evaluate_risk_level("_static_tool", {}, None) == "medium"


def test_callable_risk_evaluated_with_args(_clean_registry):
    def _risk(args, ctx):
        return "low" if args.get("safe") else "medium"

    @registry.tool(risk_level=_risk)
    def _dyn_tool(safe: bool = False) -> str:
        return "ok"

    assert registry.evaluate_risk_level("_dyn_tool", {"safe": True}, None) == "low"
    assert registry.evaluate_risk_level("_dyn_tool", {"safe": False}, None) == "medium"


def test_callable_risk_failclosed_to_medium_on_exception(_clean_registry):
    def _boom(args, ctx):
        raise RuntimeError("risk eval blew up")

    @registry.tool(risk_level=_boom)
    def _bad_tool() -> str:
        return "ok"

    assert registry.evaluate_risk_level("_bad_tool", {}, None) == "medium"


def test_get_risk_level_returns_conservative_string_for_callable(_clean_registry):
    @registry.tool(risk_level=lambda args, ctx: "low")
    def _dyn2() -> str:
        return "ok"

    # Context-free callers (e.g. trace logging) get a conservative static view.
    assert registry.get_risk_level("_dyn2") == "medium"
