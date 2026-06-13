"""Integration: agent_state.db embedded migration adds the `artifacts` table (v32)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS
from fleetent.schema_migrations import migrate


def _tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    return names


def _columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    conn.close()
    return cols


def _user_version(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    v = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    return v


def test_artifacts_table_created_with_expected_columns(tmp_path):
    db_path = tmp_path / "agent_state.db"
    db = SQLiteDatabase(path=db_path)
    migrate(db, MIGRATIONS)

    assert "artifacts" in _tables(db_path)
    assert _columns(db_path, "artifacts") == {
        "artifact_id",
        "server_id",
        "rel_path",
        "session_id",
        "user_id",
        "filename",
        "mime",
        "size",
        "created_at",
    }
    assert _user_version(db_path) >= 32


def test_migration_idempotent_and_preserves_prior_tables(tmp_path):
    db_path = tmp_path / "agent_state.db"
    db = SQLiteDatabase(path=db_path)
    migrate(db, MIGRATIONS)
    # Re-open + re-migrate: must not raise or rebuild.
    db2 = SQLiteDatabase(path=db_path)
    migrate(db2, MIGRATIONS)

    tables = _tables(db_path)
    assert "artifacts" in tables
    assert "sessions" in tables  # prior tables intact
    assert "traces" in tables
