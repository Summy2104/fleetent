"""Integration: budget_usage is per-agent, isolated in each agent_state.db.

Task 1.3 / 1.4 (retire-raw-sqlite-connect):
- Two agents accumulate budget into their own agent_state.db separately.
- Each agent sees only its own data (cross-agent read returns zero).
- Neither agent writes into the management DB.

Uses the new set_state_db / _db() injection API (not the old DB_PATH monkeypatch).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def _bind_db(module, tmp_path: Path, agent_id: str):
    from fleetent.runtime.agent_state_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path / "data"))
    db = router.agent_scope("default", agent_id).open_state_db(MIGRATIONS)
    module.set_state_db(db)
    return db


def test_two_agents_budget_isolated(tmp_path: Path) -> None:
    """Each agent's BudgetStore reads/writes only its own agent_state.db."""
    import fleetent.runtime.layered_budget as lbud

    _bind_db(lbud, tmp_path, "agent1")
    store1 = lbud.BudgetStore()
    now = datetime(2026, 6, 1, tzinfo=UTC)
    store1.add(lbud.BudgetScope.agent, "a1", 100, 50, now=now)
    u1 = store1.get(lbud.BudgetScope.agent, "a1", now=now)
    assert u1.turns == 1

    # Switch state_db to agent2 — agent1's usage must not be visible
    _bind_db(lbud, tmp_path, "agent2")
    store2 = lbud.BudgetStore()
    u2 = store2.get(lbud.BudgetScope.agent, "a1", now=now)
    assert u2.turns == 0, "agent2 DB must not see agent1 budget rows"


def test_budget_does_not_land_in_management_db(tmp_path: Path) -> None:
    """budget_usage rows must never appear in the management DB (management.db)."""
    import sqlite3

    import fleetent.runtime.layered_budget as lbud
    from tests.integration._migration_template import apply_migrations

    mgmt_db = tmp_path / "management.db"
    apply_migrations(mgmt_db)

    _bind_db(lbud, tmp_path, "agent1")
    store = lbud.BudgetStore()
    now = datetime(2026, 6, 1, tzinfo=UTC)
    store.add(lbud.BudgetScope.user, "u1", 100, 50, now=now)

    # management.db must have no budget_usage rows
    conn = sqlite3.connect(mgmt_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert "budget_usage" not in tables, "budget_usage must not exist in management DB"


def test_two_agents_accumulate_independently(tmp_path: Path) -> None:
    """Each agent's usage accumulates in its own DB without cross-contamination."""
    import fleetent.runtime.layered_budget as lbud

    now = datetime(2026, 6, 1, tzinfo=UTC)

    _bind_db(lbud, tmp_path, "agent1")
    s1 = lbud.BudgetStore()
    s1.add(lbud.BudgetScope.agent, "a1", 100, 0, now=now)
    s1.add(lbud.BudgetScope.agent, "a1", 100, 0, now=now)

    _bind_db(lbud, tmp_path, "agent2")
    s2 = lbud.BudgetStore()
    s2.add(lbud.BudgetScope.agent, "a1", 200, 0, now=now)

    # Restore agent1 DB to verify its count
    _bind_db(lbud, tmp_path, "agent1")
    s1b = lbud.BudgetStore()
    assert s1b.get(lbud.BudgetScope.agent, "a1", now=now).tokens == 200

    _bind_db(lbud, tmp_path, "agent2")
    s2b = lbud.BudgetStore()
    assert s2b.get(lbud.BudgetScope.agent, "a1", now=now).tokens == 200
