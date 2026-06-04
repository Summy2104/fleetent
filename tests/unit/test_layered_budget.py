"""Tests for five-layer cost/usage budget control (AR18)."""

from datetime import UTC, datetime

import pytest

import fleetent.runtime.layered_budget as lb
from fleetent.runtime.budget import NO_LIMIT
from fleetent.runtime.layered_budget import (
    BudgetScope,
    BudgetStore,
    BudgetWindow,
    LayeredBudgetChecker,
    LayeredBudgetConfig,
    ScopeBudget,
    ScopeUsage,
    period_for,
)
from fleetent.runtime.termination import StopReason


def _clock(dt):
    return lambda: dt


# ── enum + order (group 2) ───────────────────────────────────────────────────


def test_scope_enum_five_values():
    assert {s.value for s in BudgetScope} == {"task", "session", "user", "agent", "global"}


def test_scope_order_narrow_to_wide():
    assert (
        BudgetScope.task,
        BudgetScope.session,
        BudgetScope.user,
        BudgetScope.agent,
        BudgetScope.global_,
    ) == lb.SCOPE_ORDER


def test_unconfigured_scope_is_unlimited():
    cfg = LayeredBudgetConfig()
    sb = cfg.for_scope(BudgetScope.user)
    assert (sb.max_turns, sb.max_tokens) == (NO_LIMIT, NO_LIMIT)


def test_from_settings_only_overrides_configured(monkeypatch):
    from fleetent.config import Settings

    s = Settings(anthropic_api_key="x", agent_budget_user_tokens=5000)
    cfg = LayeredBudgetConfig.from_settings(s)
    assert cfg.for_scope(BudgetScope.user).max_tokens == 5000
    assert cfg.for_scope(BudgetScope.user).max_turns == NO_LIMIT  # not configured → unlimited


# ── ScopeUsage.add matches AR2 turns/tokens (group 3) ────────────────────────


def test_scope_usage_add_turns_tokens_match_ar2():
    from fleetent.runtime.budget import BudgetUsage

    layered, ar2 = ScopeUsage(), BudgetUsage()
    layered.add(100, 50)
    ar2.add(100, 50)
    assert (layered.turns, layered.tokens) == (ar2.turns, ar2.tokens)


# ── BudgetStore accumulation + isolation (group 3) ───────────────────────────


def test_store_add_then_get(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "DB_PATH", tmp_path / "users.db")
    now = datetime(2026, 6, 1, tzinfo=UTC)
    store = BudgetStore()
    store.add(BudgetScope.user, "u1", 100, 50, now=now)
    u = store.get(BudgetScope.user, "u1", now=now)
    assert u.turns == 1 and u.tokens == 150


def test_store_monotonic_accumulate_and_key_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "DB_PATH", tmp_path / "users.db")
    now = datetime(2026, 6, 1, tzinfo=UTC)
    store = BudgetStore()
    store.add(BudgetScope.user, "u1", 100, 0, now=now)
    store.add(BudgetScope.user, "u1", 100, 0, now=now)
    store.add(BudgetScope.user, "u2", 100, 0, now=now)
    assert store.get(BudgetScope.user, "u1", now=now).tokens == 200
    assert store.get(BudgetScope.user, "u2", now=now).tokens == 100


def test_store_rejects_task_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "DB_PATH", tmp_path / "users.db")
    with pytest.raises(ValueError):
        BudgetStore().add(BudgetScope.task, "t", 1, 1, now=datetime(2026, 6, 1, tzinfo=UTC))


def test_get_absent_returns_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "DB_PATH", tmp_path / "users.db")
    u = BudgetStore().get(BudgetScope.user, "nope", now=datetime(2026, 6, 1, tzinfo=UTC))
    assert (u.turns, u.tokens) == (0, 0)


# ── period windows (group 3.7-3.12) ──────────────────────────────────────────


def test_period_windows():
    now = datetime(2026, 6, 3, tzinfo=UTC)  # Wed
    assert period_for(BudgetWindow.lifetime, now) == "lifetime"
    assert period_for(BudgetWindow.daily, now) == "2026-06-03"
    assert period_for(BudgetWindow.monthly, now) == "2026-06"
    iso = now.isocalendar()
    assert period_for(BudgetWindow.weekly, now) == f"{iso.year}-W{iso.week:02d}"


def test_period_rollover_resets(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "DB_PATH", tmp_path / "users.db")
    store = BudgetStore()  # user default weekly
    wk1 = datetime(2026, 6, 1, tzinfo=UTC)
    wk_next = datetime(2026, 6, 15, tzinfo=UTC)  # later week
    store.add(BudgetScope.user, "u1", 100, 0, now=wk1)
    assert store.get(BudgetScope.user, "u1", now=wk_next).tokens == 0  # new period, fresh


def test_lifetime_accumulates_across_calendar(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "DB_PATH", tmp_path / "users.db")
    store = BudgetStore()  # session default lifetime
    store.add(BudgetScope.session, "s1", 100, 0, now=datetime(2026, 6, 1, tzinfo=UTC))
    later = store.get(BudgetScope.session, "s1", now=datetime(2026, 12, 1, tzinfo=UTC))
    assert later.tokens == 100  # lifetime period constant


# ── LayeredBudgetChecker (group 4) ───────────────────────────────────────────


def test_checker_triggers_on_scope_over(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "DB_PATH", tmp_path / "users.db")
    now = datetime(2026, 6, 1, tzinfo=UTC)
    store = BudgetStore()
    store.add(BudgetScope.user, "u1", 6000, 0, now=now)
    cfg = LayeredBudgetConfig({BudgetScope.user: ScopeBudget(max_tokens=5000)})
    chk = LayeredBudgetChecker(
        cfg, store, {BudgetScope.user: "u1", BudgetScope.global_: lb.GLOBAL_KEY}, clock=_clock(now)
    )
    assert chk.check(None) is StopReason.budget_exceeded
    assert chk.triggered_scope == "user" and chk.triggered_dimension == "tokens"


def test_checker_narrowest_scope_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "DB_PATH", tmp_path / "users.db")
    now = datetime(2026, 6, 1, tzinfo=UTC)
    store = BudgetStore()
    store.add(BudgetScope.user, "u1", 6000, 0, now=now)
    store.add(BudgetScope.global_, lb.GLOBAL_KEY, 6000, 0, now=now)
    cfg = LayeredBudgetConfig(
        {
            BudgetScope.user: ScopeBudget(max_tokens=5000),
            BudgetScope.global_: ScopeBudget(max_tokens=5000),
        }
    )
    chk = LayeredBudgetChecker(
        cfg, store, {BudgetScope.user: "u1", BudgetScope.global_: lb.GLOBAL_KEY}, clock=_clock(now)
    )
    assert chk.check(None) is StopReason.budget_exceeded
    assert chk.triggered_scope == "user"  # narrower reported


def test_checker_skips_missing_key(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "DB_PATH", tmp_path / "users.db")
    now = datetime(2026, 6, 1, tzinfo=UTC)
    store = BudgetStore()
    cfg = LayeredBudgetConfig({BudgetScope.user: ScopeBudget(max_tokens=1)})
    chk = LayeredBudgetChecker(cfg, store, {BudgetScope.user: None}, clock=_clock(now))
    assert chk.check(None) is None  # no user key → user scope skipped


# ── agent_loop wiring (group 6) ──────────────────────────────────────────────


async def test_agent_loop_dormant_without_caps(monkeypatch, tmp_path):
    """Default (no caps): layered budget is dormant — no checker, no DB written."""
    import fleetent.runtime.layered_budget as lbud
    import fleetent.runtime.loop as al

    monkeypatch.setattr(lbud, "DB_PATH", tmp_path / "users.db")
    checker, store, keys = al._setup_layered_budget("s", "u", "a")
    assert checker is None and store is None  # all NO_LIMIT → dormant
    assert not (tmp_path / "users.db").exists()  # no DB touched
