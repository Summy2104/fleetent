"""DB-backed layered budget store and runtime wiring tests."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

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


def _bind_db(tmp_path: Path, agent_id: str = "agent"):
    import fleetent.runtime.layered_budget as lb
    from fleetent.runtime.agent_state_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path / "data"))
    db = router.agent_scope("default", agent_id).open_state_db(MIGRATIONS)
    lb.set_state_db(db)
    return db


def test_store_add_then_get(tmp_path):
    _bind_db(tmp_path)
    now = datetime(2026, 6, 1, tzinfo=UTC)
    store = BudgetStore()
    store.add(BudgetScope.user, "u1", 100, 50, now=now)
    u = store.get(BudgetScope.user, "u1", now=now)
    assert u.turns == 1 and u.tokens == 150


def test_store_monotonic_accumulate_and_key_isolation(tmp_path):
    _bind_db(tmp_path)
    now = datetime(2026, 6, 1, tzinfo=UTC)
    store = BudgetStore()
    store.add(BudgetScope.user, "u1", 100, 0, now=now)
    store.add(BudgetScope.user, "u1", 100, 0, now=now)
    store.add(BudgetScope.user, "u2", 100, 0, now=now)
    assert store.get(BudgetScope.user, "u1", now=now).tokens == 200
    assert store.get(BudgetScope.user, "u2", now=now).tokens == 100


def test_store_rejects_task_scope(tmp_path):
    _bind_db(tmp_path)
    with pytest.raises(ValueError):
        BudgetStore().add(BudgetScope.task, "t", 1, 1, now=datetime(2026, 6, 1, tzinfo=UTC))


def test_get_absent_returns_zero(tmp_path):
    _bind_db(tmp_path)
    u = BudgetStore().get(BudgetScope.user, "nope", now=datetime(2026, 6, 1, tzinfo=UTC))
    assert (u.turns, u.tokens) == (0, 0)


def test_period_rollover_resets(tmp_path):
    _bind_db(tmp_path)
    store = BudgetStore()  # user default weekly
    wk1 = datetime(2026, 6, 1, tzinfo=UTC)
    wk_next = datetime(2026, 6, 15, tzinfo=UTC)  # later week
    store.add(BudgetScope.user, "u1", 100, 0, now=wk1)
    assert store.get(BudgetScope.user, "u1", now=wk_next).tokens == 0  # new period, fresh


def test_lifetime_accumulates_across_calendar(tmp_path):
    _bind_db(tmp_path)
    store = BudgetStore()  # session default lifetime
    store.add(BudgetScope.session, "s1", 100, 0, now=datetime(2026, 6, 1, tzinfo=UTC))
    later = store.get(BudgetScope.session, "s1", now=datetime(2026, 12, 1, tzinfo=UTC))
    assert later.tokens == 100  # lifetime period constant


def test_checker_triggers_on_scope_over(tmp_path):
    _bind_db(tmp_path)
    now = datetime(2026, 6, 1, tzinfo=UTC)
    store = BudgetStore()
    store.add(BudgetScope.user, "u1", 6000, 0, now=now)
    cfg = LayeredBudgetConfig({BudgetScope.user: ScopeBudget(max_tokens=5000)})
    chk = LayeredBudgetChecker(cfg, store, {BudgetScope.user: "u1"}, clock=_clock(now))
    assert chk.check(None) is StopReason.budget_exceeded
    assert chk.triggered_scope == "user" and chk.triggered_dimension == "tokens"


def test_checker_narrowest_scope_wins(tmp_path):
    _bind_db(tmp_path)
    now = datetime(2026, 6, 1, tzinfo=UTC)
    store = BudgetStore()
    store.add(BudgetScope.user, "u1", 6000, 0, now=now)
    store.add(BudgetScope.agent, "a1", 6000, 0, now=now)
    cfg = LayeredBudgetConfig(
        {
            BudgetScope.user: ScopeBudget(max_tokens=5000),
            BudgetScope.agent: ScopeBudget(max_tokens=5000),
        }
    )
    chk = LayeredBudgetChecker(
        cfg, store, {BudgetScope.user: "u1", BudgetScope.agent: "a1"}, clock=_clock(now)
    )
    assert chk.check(None) is StopReason.budget_exceeded
    assert chk.triggered_scope == "user"  # narrower reported


def test_checker_skips_missing_key(tmp_path):
    _bind_db(tmp_path)
    now = datetime(2026, 6, 1, tzinfo=UTC)
    store = BudgetStore()
    cfg = LayeredBudgetConfig({BudgetScope.user: ScopeBudget(max_tokens=1)})
    chk = LayeredBudgetChecker(cfg, store, {BudgetScope.user: None}, clock=_clock(now))
    assert chk.check(None) is None  # no user key -> user scope skipped


async def test_agent_loop_dormant_without_caps(tmp_path):
    """Default (no caps): layered budget is dormant — no checker, no DB written."""
    import fleetent.runtime.layered_budget as lbud
    import fleetent.runtime.loop as al

    # Even with state_db injected, dormant config must not touch it
    _bind_db(tmp_path)
    checker, store, keys = al._setup_layered_budget("s", "u", "a")
    assert checker is None and store is None  # all NO_LIMIT -> dormant
