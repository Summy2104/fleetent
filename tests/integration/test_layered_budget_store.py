"""DB-backed layered budget store and runtime wiring tests."""

from datetime import UTC, datetime

import pytest

import fleetent.runtime.layered_budget as lb
from fleetent.runtime.layered_budget import (
    BudgetScope,
    BudgetStore,
    LayeredBudgetChecker,
    LayeredBudgetConfig,
    ScopeBudget,
)
from fleetent.runtime.termination import StopReason


def _clock(dt):
    return lambda: dt


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
    assert chk.check(None) is None  # no user key -> user scope skipped


async def test_agent_loop_dormant_without_caps(monkeypatch, tmp_path):
    """Default (no caps): layered budget is dormant - no checker, no DB written."""
    import fleetent.runtime.layered_budget as lbud
    import fleetent.runtime.loop as al

    monkeypatch.setattr(lbud, "DB_PATH", tmp_path / "users.db")
    checker, store, keys = al._setup_layered_budget("s", "u", "a")
    assert checker is None and store is None  # all NO_LIMIT -> dormant
    assert not (tmp_path / "users.db").exists()  # no DB touched
