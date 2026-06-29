"""Integration: the embedded migration engine tolerates dual-authority column overlap.

Agent-side libraries use ``CREATE TABLE IF NOT EXISTS`` so a table another authority
(Alembic, in mixed test DBs) already created is a benign no-op. ``ALTER TABLE ... ADD
COLUMN`` has no SQL ``IF NOT EXISTS`` equivalent, so the engine treats a "duplicate column
name" on an ADD COLUMN as already-applied (the column is present) — advancing the version
stamp without error. Any other failure still raises ``MigrationError``.
"""

from __future__ import annotations

import sqlite3

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.schema_migrations import MigrationError, migrate


def _version(path) -> int:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def test_add_column_is_idempotent_when_column_preexists(tmp_path):
    db_path = tmp_path / "x.db"
    db = SQLiteDatabase(path=db_path)
    # Another authority already created the table WITH the column (mixed-schema test DB).
    db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, kind TEXT NOT NULL DEFAULT 'oauth')")
    migrations = [
        (1, "CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY)"),
        (2, "ALTER TABLE t ADD COLUMN kind TEXT NOT NULL DEFAULT 'oauth'"),
    ]
    migrate(db, migrations)  # must NOT raise even though `kind` already exists
    assert _version(db_path) == 2


def test_add_column_runs_normally_on_fresh_db(tmp_path):
    db_path = tmp_path / "y.db"
    db = SQLiteDatabase(path=db_path)
    migrations = [
        (1, "CREATE TABLE t (id INTEGER PRIMARY KEY)"),
        (2, "ALTER TABLE t ADD COLUMN kind TEXT NOT NULL DEFAULT 'oauth'"),
    ]
    migrate(db, migrations)
    assert _version(db_path) == 2
    cols = {r["name"] for r in db.execute("PRAGMA table_info(t)").fetchall()}
    assert "kind" in cols


def test_non_duplicate_error_still_raises(tmp_path):
    db_path = tmp_path / "z.db"
    db = SQLiteDatabase(path=db_path)
    migrations = [(1, "ALTER TABLE does_not_exist ADD COLUMN k TEXT")]
    with pytest.raises(MigrationError):
        migrate(db, migrations)
    assert _version(db_path) == 0  # version not advanced on a genuine failure
