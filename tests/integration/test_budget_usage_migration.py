"""Integration: budget_usage table created by unified AGENT_STATE_MIGRATIONS.

Verifies that opening a fresh agent_state.db via the unified MIGRATIONS produces the
budget_usage table with the exact columns from the original layered_budget.init_db DDL.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def _open_agent_db(tmp_path: Path, agent_id: str = "agent"):
    from fleetent.runtime.agent_state_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path / "data"))
    return router.agent_scope("default", agent_id).open_state_db(MIGRATIONS)


def _tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    names = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    conn.close()
    return names


def _columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    conn.close()
    return cols


def test_budget_usage_table_exists_after_migrations(tmp_path: Path) -> None:
    db = _open_agent_db(tmp_path)
    assert "budget_usage" in _tables(db.path), (
        "budget_usage must be created by unified AGENT_STATE_MIGRATIONS"
    )


def test_budget_usage_columns_match_original_ddl(tmp_path: Path) -> None:
    db = _open_agent_db(tmp_path)
    cols = _columns(db.path, "budget_usage")
    assert cols == {"scope", "key", "period", "turns", "tokens"}, (
        f"budget_usage columns {cols!r} must match the original init_db DDL"
    )
