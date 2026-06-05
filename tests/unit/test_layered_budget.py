"""Tests for five-layer cost/usage budget control (AR18)."""

from datetime import UTC, datetime

import fleetent.runtime.layered_budget as lb
from fleetent.runtime.budget import NO_LIMIT
from fleetent.runtime.layered_budget import (
    BudgetScope,
    BudgetWindow,
    LayeredBudgetConfig,
    ScopeUsage,
    period_for,
)

# ── enum + order (group 2) ───────────────────────────────────────────────────


def test_scope_enum_four_values_no_global():
    # global dropped: distributed per-agent processes have no cross-agent aggregation.
    assert {s.value for s in BudgetScope} == {"task", "session", "user", "agent"}


def test_scope_order_narrow_to_wide():
    assert (
        BudgetScope.task,
        BudgetScope.session,
        BudgetScope.user,
        BudgetScope.agent,
    ) == lb.SCOPE_ORDER


def test_cross_run_scopes_exclude_global():
    assert lb.CROSS_RUN_SCOPES == (
        BudgetScope.session,
        BudgetScope.user,
        BudgetScope.agent,
    )


def test_unconfigured_scope_is_unlimited():
    cfg = LayeredBudgetConfig()
    sb = cfg.for_scope(BudgetScope.user)
    assert (sb.max_turns, sb.max_tokens) == (NO_LIMIT, NO_LIMIT)


def test_from_governance_only_overrides_configured():
    from fleetent.runtime.snapshot import GovernanceConfig

    g = GovernanceConfig(agent_budget_user_tokens=5000)
    cfg = LayeredBudgetConfig.from_governance(g)
    assert cfg.for_scope(BudgetScope.user).max_tokens == 5000
    assert cfg.for_scope(BudgetScope.user).max_turns == NO_LIMIT  # not configured → unlimited


# ── ScopeUsage.add matches AR2 turns/tokens (group 3) ────────────────────────


def test_scope_usage_add_turns_tokens_match_ar2():
    from fleetent.runtime.budget import BudgetUsage

    layered, ar2 = ScopeUsage(), BudgetUsage()
    layered.add(100, 50)
    ar2.add(100, 50)
    assert (layered.turns, layered.tokens) == (ar2.turns, ar2.tokens)


# ── period windows (group 3.7-3.12) ──────────────────────────────────────────


def test_period_windows():
    now = datetime(2026, 6, 3, tzinfo=UTC)  # Wed
    assert period_for(BudgetWindow.lifetime, now) == "lifetime"
    assert period_for(BudgetWindow.daily, now) == "2026-06-03"
    assert period_for(BudgetWindow.monthly, now) == "2026-06"
    iso = now.isocalendar()
    assert period_for(BudgetWindow.weekly, now) == f"{iso.year}-W{iso.week:02d}"
