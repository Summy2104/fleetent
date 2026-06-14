"""Unit tests for the two-dimensional iteration budget (AR2: turns / tokens)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from fleetent.runtime import budget as bud
from fleetent.runtime.budget import (
    NO_LIMIT,
    BudgetChecker,
    BudgetConfig,
    BudgetUsage,
    grace_max_tokens,
)
from fleetent.runtime.termination import LoopState, StopReason

# ── BudgetConfig / BudgetUsage shape ───────────────────────────────────────────


def test_budget_config_holds_two_dimensions() -> None:
    cfg = BudgetConfig(max_turns=10, max_tokens=1000)
    assert cfg.max_turns == 10
    assert cfg.max_tokens == 1000


def test_budget_config_is_frozen() -> None:
    cfg = BudgetConfig(max_turns=10, max_tokens=1000)
    with pytest.raises(FrozenInstanceError):
        cfg.max_turns = 5  # type: ignore[misc]


def test_budget_config_supports_no_limit_sentinel() -> None:
    cfg = BudgetConfig(max_turns=NO_LIMIT, max_tokens=NO_LIMIT)
    assert cfg.max_turns == NO_LIMIT


def test_usage_tracker_starts_at_zero() -> None:
    usage = BudgetUsage()
    assert usage.turns == 0
    assert usage.tokens == 0


# ── cost dimension is gone (review-removed) ─────────────────────────────────────


def test_budget_config_has_no_cost_dimension() -> None:
    assert not hasattr(BudgetConfig(max_turns=1, max_tokens=1), "max_cost_usd")


def test_usage_tracker_has_no_cost_dimension() -> None:
    assert not hasattr(BudgetUsage(), "cost_usd")


def test_budget_module_has_no_pricing_tables() -> None:
    assert not hasattr(bud, "MODEL_PRICING")
    assert not hasattr(bud, "DEFAULT_PRICING")


# ── BudgetUsage.add: token + turn accumulation ──────────────────────────────────


def test_usage_add_accumulates_turns_and_tokens() -> None:
    usage = BudgetUsage()
    usage.add(100, 50)
    usage.add(200, 80)
    assert usage.turns == 2
    assert usage.tokens == 100 + 50 + 200 + 80


# ── "about to exhaust" judgement + triggering dimension ─────────────────────────


def test_exhausted_when_turns_reach_limit() -> None:
    cfg = BudgetConfig(max_turns=3, max_tokens=NO_LIMIT)
    usage = BudgetUsage(turns=3)
    assert cfg.exhausted_dimension(usage) == "turns"


def test_exhausted_when_tokens_reach_limit() -> None:
    cfg = BudgetConfig(max_turns=NO_LIMIT, max_tokens=500)
    usage = BudgetUsage(tokens=500)
    assert cfg.exhausted_dimension(usage) == "tokens"


def test_not_exhausted_below_all_limits() -> None:
    cfg = BudgetConfig(max_turns=10, max_tokens=1000)
    usage = BudgetUsage(turns=5, tokens=500)
    assert cfg.exhausted_dimension(usage) is None


def test_no_limit_dimension_never_triggers() -> None:
    cfg = BudgetConfig(max_turns=NO_LIMIT, max_tokens=NO_LIMIT)
    usage = BudgetUsage(turns=10**9, tokens=10**9)
    assert cfg.exhausted_dimension(usage) is None


def test_turns_dimension_checked_first() -> None:
    # When several dimensions are simultaneously over, the reported dimension is
    # deterministic: turns > tokens.
    cfg = BudgetConfig(max_turns=1, max_tokens=1)
    usage = BudgetUsage(turns=5, tokens=5)
    assert cfg.exhausted_dimension(usage) == "turns"


# ── BudgetChecker (AR1 framework) ───────────────────────────────────────────────


def test_budget_checker_returns_budget_exceeded_when_over() -> None:
    cfg = BudgetConfig(max_turns=2, max_tokens=NO_LIMIT)
    usage = BudgetUsage(turns=2)
    checker = BudgetChecker(cfg, usage)
    assert checker.check(LoopState()) == StopReason.budget_exceeded


def test_budget_checker_returns_none_when_under() -> None:
    cfg = BudgetConfig(max_turns=10, max_tokens=NO_LIMIT)
    usage = BudgetUsage(turns=2)
    checker = BudgetChecker(cfg, usage)
    assert checker.check(LoopState()) is None


def test_budget_checker_exposes_triggered_dimension() -> None:
    cfg = BudgetConfig(max_turns=NO_LIMIT, max_tokens=100)
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
