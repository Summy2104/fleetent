"""Integration: the retired cross-run budget table is absent at migration head."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fleetent.db import SQLiteDatabase
from fleetent.schema_migrations import migrate

_RETIRED_TABLE = "_".join(("budget", "usage"))


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


def test_retired_budget_table_absent_after_migrations(tmp_path: Path) -> None:
    db = _open_agent_db(tmp_path)
    assert _RETIRED_TABLE not in _tables(db.path), (
        "the retired cross-run budget table must be absent at the current head"
    )


def test_retired_budget_table_dropped_when_legacy_db_migrates_to_head(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS

    db_path = tmp_path / "agent_state.db"
    pre_drop = [migration for migration in MIGRATIONS if migration[0] < MIGRATIONS[-1][0]]
    migrate(SQLiteDatabase(path=db_path), pre_drop)

    conn = sqlite3.connect(db_path)
    conn.execute(
        f"INSERT INTO {_RETIRED_TABLE} (scope, key, period, turns, tokens) VALUES (?, ?, ?, ?, ?)",
        ("user", "u1", "2026-06", 3, 120),
    )
    conn.commit()
    conn.close()

    migrate(SQLiteDatabase(path=db_path), MIGRATIONS)

    assert _RETIRED_TABLE not in _tables(db_path), (
        "legacy rows for the retired cross-run budget table must be dropped at head"
    )
