"""Unit tests for the three-dimensional iteration budget (AR2)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from fleetent import budget as bud
from fleetent.budget import (
    DEFAULT_PRICING,
    MODEL_PRICING,
    NO_LIMIT,
    BudgetChecker,
    BudgetConfig,
    BudgetUsage,
    grace_max_tokens,
)
from fleetent.termination import LoopState, StopReason

# ── BudgetConfig / BudgetUsage shape ───────────────────────────────────────────


def test_budget_config_holds_three_dimensions() -> None:
    cfg = BudgetConfig(max_turns=10, max_tokens=1000, max_cost_usd=1.0)
    assert cfg.max_turns == 10
    assert cfg.max_tokens == 1000
    assert cfg.max_cost_usd == 1.0


def test_budget_config_is_frozen() -> None:
    cfg = BudgetConfig(max_turns=10, max_tokens=1000, max_cost_usd=1.0)
    with pytest.raises(FrozenInstanceError):
        cfg.max_turns = 5  # type: ignore[misc]


def test_budget_config_supports_no_limit_sentinel() -> None:
    cfg = BudgetConfig(max_turns=NO_LIMIT, max_tokens=NO_LIMIT, max_cost_usd=NO_LIMIT)
    assert cfg.max_turns == NO_LIMIT


def test_budget_usage_starts_at_zero() -> None:
    usage = BudgetUsage()
    assert usage.turns == 0
    assert usage.tokens == 0
    assert usage.cost_usd == 0.0


# ── BudgetUsage.add: token + turn + cost accumulation ───────────────────────────


def test_usage_add_accumulates_turns_and_tokens() -> None:
    usage = BudgetUsage()
    usage.add(100, 50, "claude-sonnet-4-5")
    usage.add(200, 80, "claude-sonnet-4-5")
    assert usage.turns == 2
    assert usage.tokens == 100 + 50 + 200 + 80


def test_usage_add_computes_cost_from_pricing_table() -> None:
    usage = BudgetUsage()
    model = "claude-sonnet-4-5"
    in_price, out_price = MODEL_PRICING[model]
    usage.add(1000, 1000, model)
    # prices are USD per 1K tokens
    expected = in_price + out_price
    assert usage.cost_usd == pytest.approx(expected)


def test_usage_add_unknown_model_uses_default_pricing_never_zero() -> None:
    usage = BudgetUsage()
    usage.add(1000, 1000, "some-unlisted-model-xyz")
    in_price, out_price = DEFAULT_PRICING
    assert in_price > 0 and out_price > 0
    assert usage.cost_usd == pytest.approx(in_price + out_price)
    assert usage.cost_usd > 0


def test_pricing_table_is_monkeypatchable(monkeypatch) -> None:
    monkeypatch.setitem(MODEL_PRICING, "fake-model", (1.0, 2.0))
    usage = BudgetUsage()
    usage.add(1000, 1000, "fake-model")
    assert usage.cost_usd == pytest.approx(3.0)


# ── "about to exhaust" judgement + triggering dimension ─────────────────────────


def test_exhausted_when_turns_reach_limit() -> None:
    cfg = BudgetConfig(max_turns=3, max_tokens=NO_LIMIT, max_cost_usd=NO_LIMIT)
    usage = BudgetUsage(turns=3)
    assert cfg.exhausted_dimension(usage) == "turns"


def test_exhausted_when_tokens_reach_limit() -> None:
    cfg = BudgetConfig(max_turns=NO_LIMIT, max_tokens=500, max_cost_usd=NO_LIMIT)
    usage = BudgetUsage(tokens=500)
    assert cfg.exhausted_dimension(usage) == "tokens"


def test_exhausted_when_cost_reaches_limit() -> None:
    cfg = BudgetConfig(max_turns=NO_LIMIT, max_tokens=NO_LIMIT, max_cost_usd=0.5)
    usage = BudgetUsage(cost_usd=0.5)
    assert cfg.exhausted_dimension(usage) == "cost_usd"


def test_not_exhausted_below_all_limits() -> None:
    cfg = BudgetConfig(max_turns=10, max_tokens=1000, max_cost_usd=1.0)
    usage = BudgetUsage(turns=5, tokens=500, cost_usd=0.5)
    assert cfg.exhausted_dimension(usage) is None


def test_no_limit_dimension_never_triggers() -> None:
    cfg = BudgetConfig(max_turns=NO_LIMIT, max_tokens=NO_LIMIT, max_cost_usd=NO_LIMIT)
    usage = BudgetUsage(turns=10**9, tokens=10**9, cost_usd=10.0**9)
    assert cfg.exhausted_dimension(usage) is None


def test_turns_dimension_checked_first() -> None:
    # When several dimensions are simultaneously over, the reported dimension is
    # deterministic: turns > tokens > cost_usd.
    cfg = BudgetConfig(max_turns=1, max_tokens=1, max_cost_usd=0.0)
    usage = BudgetUsage(turns=5, tokens=5, cost_usd=5.0)
    assert cfg.exhausted_dimension(usage) == "turns"


# ── BudgetChecker (AR1 framework) ───────────────────────────────────────────────


def test_budget_checker_returns_budget_exceeded_when_over() -> None:
    cfg = BudgetConfig(max_turns=2, max_tokens=NO_LIMIT, max_cost_usd=NO_LIMIT)
    usage = BudgetUsage(turns=2)
    checker = BudgetChecker(cfg, usage)
    assert checker.check(LoopState()) == StopReason.budget_exceeded


def test_budget_checker_returns_none_when_under() -> None:
    cfg = BudgetConfig(max_turns=10, max_tokens=NO_LIMIT, max_cost_usd=NO_LIMIT)
    usage = BudgetUsage(turns=2)
    checker = BudgetChecker(cfg, usage)
    assert checker.check(LoopState()) is None


def test_budget_checker_exposes_triggered_dimension() -> None:
    cfg = BudgetConfig(max_turns=NO_LIMIT, max_tokens=100, max_cost_usd=NO_LIMIT)
    usage = BudgetUsage(tokens=100)
    checker = BudgetChecker(cfg, usage)
    checker.check(LoopState())
    assert checker.triggered_dimension == "tokens"


# ── Grace Call reserved budget ──────────────────────────────────────────────────


def test_grace_max_tokens_uses_ratio() -> None:
    assert grace_max_tokens(100_000, ratio=0.05, floor=512) == 5000


def test_grace_max_tokens_applies_floor_when_ratio_small() -> None:
    assert grace_max_tokens(1000, ratio=0.05, floor=512) == 512


def test_grace_max_tokens_no_limit_main_budget_uses_floor() -> None:
    # When the main token budget is unlimited, ratio * NO_LIMIT is meaningless;
    # fall back to the floor so the grace call still gets a usable cap.
    result = grace_max_tokens(NO_LIMIT, ratio=0.05, floor=512)
    assert result == 512


def test_grace_max_tokens_rounds() -> None:
    assert grace_max_tokens(10_001, ratio=0.05, floor=1) == round(10_001 * 0.05)


def test_grace_defaults_from_settings(monkeypatch) -> None:
    # Defaults are pulled from Settings when ratio/floor are not passed.
    monkeypatch.setattr(bud, "_grace_defaults", lambda: (0.1, 256))
    assert grace_max_tokens(10_000) == 1000
