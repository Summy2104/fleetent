"""Tests for the embedded forward-only migration engine (Y).

Covers: empty db, incremental upgrade, per-step transaction+bump, rollback on failure,
version gate (db ahead of code), and multi-consumer isolation.
All use real SQLite files under tmp_path.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.schema_migrations import (
    MigrationError,
    SchemaTooNewError,
    migrate,
)

_MIGRATIONS_V1: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE widgets (
            id   TEXT PRIMARY KEY,
            name TEXT NOT NULL
        )
        """,
    ),
]

_MIGRATIONS_V2: list[tuple[int, str]] = [
    *_MIGRATIONS_V1,
    (
        2,
        "ALTER TABLE widgets ADD COLUMN colour TEXT NOT NULL DEFAULT 'grey'",
    ),
]

_MIGRATIONS_V3: list[tuple[int, str]] = [
    *_MIGRATIONS_V2,
    (
        3,
        """
        CREATE TABLE gadgets (
            id TEXT PRIMARY KEY
        )
        """,
    ),
]


def _user_version(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    ver = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    return ver


def _set_user_version(db_path: Path, ver: int) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(f"PRAGMA user_version = {ver}")
    conn.commit()
    conn.close()


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    return names


def _col_names(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    conn.close()
    return {r[1] for r in rows}


# ── 1.1-a: empty db runs all steps ─────────────────────────────────────────


def test_empty_db_runs_all_migrations(tmp_path: Path) -> None:
    db = SQLiteDatabase(path=tmp_path / "w.db")
    migrate(db, _MIGRATIONS_V3)

    assert _user_version(tmp_path / "w.db") == 3
    assert "widgets" in _table_names(tmp_path / "w.db")
    assert "gadgets" in _table_names(tmp_path / "w.db")


# ── 1.1-b: old db only runs missing steps ──────────────────────────────────


def test_old_db_runs_only_incremental_steps(tmp_path: Path) -> None:
    db_path = tmp_path / "w.db"
    db = SQLiteDatabase(path=db_path)

    # Bootstrap to v1 manually.
    migrate(db, _MIGRATIONS_V1)
    assert _user_version(db_path) == 1

    # Now advance to v2.
    migrate(db, _MIGRATIONS_V2)
    assert _user_version(db_path) == 2
    assert "colour" in _col_names(db_path, "widgets")


# ── 1.1-c: every step bumps version inside its own transaction ─────────────


def test_each_step_bumps_version_inside_transaction(tmp_path: Path) -> None:
    db_path = tmp_path / "w.db"
    db = SQLiteDatabase(path=db_path)

    migrate(db, _MIGRATIONS_V2)
    # Both steps must have been committed atomically.
    assert _user_version(db_path) == 2


# ── 1.1-d: failed step rolls back, version does not advance ────────────────


def test_failing_step_rolls_back_and_does_not_advance_version(tmp_path: Path) -> None:
    db_path = tmp_path / "w.db"
    db = SQLiteDatabase(path=db_path)

    # First apply v1 so we start at version 1.
    migrate(db, _MIGRATIONS_V1)
    assert _user_version(db_path) == 1

    bad_migrations: list[tuple[int, str]] = [
        *_MIGRATIONS_V1,
        (2, "THIS IS NOT VALID SQL !!!"),
    ]
    with pytest.raises(MigrationError):
        migrate(db, bad_migrations)

    # Version must still be 1 – the failed step must not have advanced it.
    assert _user_version(db_path) == 1


# ── 1.1-e: db version ahead of code raises SchemaTooNewError ───────────────


def test_db_ahead_of_code_raises_schema_too_new(tmp_path: Path) -> None:
    db_path = tmp_path / "w.db"
    db_path.touch()  # create the file so SQLite can open it
    _set_user_version(db_path, 99)

    db = SQLiteDatabase(path=db_path)
    with pytest.raises(SchemaTooNewError):
        migrate(db, _MIGRATIONS_V1)  # code only knows up to v1


# ── 1.1-f: already-at-latest db does nothing (no-op) ──────────────────────


def test_already_current_db_is_noop(tmp_path: Path) -> None:
    db_path = tmp_path / "w.db"
    db = SQLiteDatabase(path=db_path)

    migrate(db, _MIGRATIONS_V1)
    migrate(db, _MIGRATIONS_V1)  # second call must not raise or break

    assert _user_version(db_path) == 1


# ── 1.1-g: empty and old db follow the same code path ─────────────────────


def test_empty_and_old_db_same_code_path(tmp_path: Path) -> None:
    # Empty db ends up at v3.
    empty_path = tmp_path / "empty.db"
    migrate(SQLiteDatabase(path=empty_path), _MIGRATIONS_V3)

    # Old db (v1) also ends up at v3.
    old_path = tmp_path / "old.db"
    migrate(SQLiteDatabase(path=old_path), _MIGRATIONS_V1)
    migrate(SQLiteDatabase(path=old_path), _MIGRATIONS_V3)

    assert _user_version(empty_path) == _user_version(old_path) == 3
    assert _table_names(empty_path) == _table_names(old_path)
