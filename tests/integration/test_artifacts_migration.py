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
        "scope_key",
        "session_id",
        "user_id",
        "filename",
        "mime",
        "size",
        "created_at",
    }
    assert _user_version(db_path) >= 36


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


def test_scope_key_column_add_preserves_prior_artifact_rows(tmp_path):
    """An artifacts row created before scope_key (v35) survives the v36 column add.

    Reconcile note: artifacts is v35 and scope_key is v36 (renumbered after Bitbucket's
    v32-v34); the pre-scope_key slice is therefore `<= 35`, not `<= 32`.
    """
    db_path = tmp_path / "agent_state.db"
    # Migrate only up to v35 (artifacts created, no scope_key yet), insert a legacy row.
    pre_scope = [m for m in MIGRATIONS if m[0] <= 35]
    db = SQLiteDatabase(path=db_path)
    migrate(db, pre_scope)
    assert "scope_key" not in _columns(db_path, "artifacts")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO artifacts (artifact_id, server_id, rel_path, session_id) "
        "VALUES ('a1', 'srv', 'out/x.txt', 's1')"
    )
    conn.commit()
    conn.close()

    # Re-open with the full migration set: v33 must add scope_key, row intact.
    migrate(SQLiteDatabase(path=db_path), MIGRATIONS)
    assert "scope_key" in _columns(db_path, "artifacts")
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT artifact_id, session_id, scope_key FROM artifacts WHERE artifact_id='a1'"
    ).fetchone()
    conn.close()
    assert row == ("a1", "s1", None)  # legacy row preserved; scope_key NULL until re-registered
    assert _user_version(db_path) >= 36
