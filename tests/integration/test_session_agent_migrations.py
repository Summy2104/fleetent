"""Integration tests: per-agent MIGRATIONS contains session metadata DDL (3b-1).

Verifies that after running Y migrate-on-open on an empty per-agent DB:
- the 'sessions' table exists with the expected columns
- user_version is stamped correctly
- schema matches what session/index.py ensure_schema used to create
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fleetent.db import SQLiteDatabase
from fleetent.schema_migrations import migrate
from fleetent.session.migrations import MIGRATIONS as SESSION_MIGRATIONS


def _open(tmp_path: Path) -> SQLiteDatabase:
    return SQLiteDatabase(path=tmp_path / "agent_state.db")


def _user_version(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    v = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    return v


def _columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    conn.close()
    return cols


# ── 1: MIGRATIONS exists and is non-empty ─────────────────────────────────


def test_session_migrations_is_non_empty() -> None:
    assert len(SESSION_MIGRATIONS) >= 1
    assert all(isinstance(v, int) and isinstance(sql, str) for v, sql in SESSION_MIGRATIONS)


# ── 2: after migrate, sessions table exists ────────────────────────────────


def test_migrate_creates_sessions_table(tmp_path: Path) -> None:
    db = _open(tmp_path)
    migrate(db, SESSION_MIGRATIONS)
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
    ).fetchone()
    assert row is not None


# ── 3: sessions table has expected columns (DDL-equivalent to old ensure_schema) ──


def test_sessions_table_columns_match_old_ensure_schema(tmp_path: Path) -> None:
    db = _open(tmp_path)
    migrate(db, SESSION_MIGRATIONS)
    cols = _columns(db.path, "sessions")
    assert cols == {
        "session_id",
        "user_id",
        "created_at",
        "updated_at",
        "message_count",
        "agent_name",
    }


# ── 4: user_version is stamped ────────────────────────────────────────────


def test_user_version_stamped_after_migrate(tmp_path: Path) -> None:
    db = _open(tmp_path)
    migrate(db, SESSION_MIGRATIONS)
    expected = max(v for v, _ in SESSION_MIGRATIONS)
    assert _user_version(db.path) == expected


# ── 5: idempotent ────────────────────────────────────────────────────────


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    db = _open(tmp_path)
    migrate(db, SESSION_MIGRATIONS)
    migrate(db, SESSION_MIGRATIONS)  # second call must not raise
    assert _user_version(db.path) == max(v for v, _ in SESSION_MIGRATIONS)
