"""Multi-consumer independence tests for the Y migration engine.

The same engine instance must be able to drive two independent DBs with
completely different MIGRATIONS lists without either interfering with the other.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fleetent.db import SQLiteDatabase
from fleetent.schema_migrations import migrate

_WIDGETS: list[tuple[int, str]] = [
    (1, "CREATE TABLE widgets (id TEXT PRIMARY KEY, name TEXT NOT NULL)"),
    (2, "ALTER TABLE widgets ADD COLUMN colour TEXT NOT NULL DEFAULT 'grey'"),
]

_GADGETS: list[tuple[int, str]] = [
    (1, "CREATE TABLE gadgets (id TEXT PRIMARY KEY, model TEXT NOT NULL)"),
]


def _user_version(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    ver = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    return ver


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    return names


def test_two_independent_dbs_do_not_interfere(tmp_path: Path) -> None:
    widgets_path = tmp_path / "widgets.db"
    gadgets_path = tmp_path / "gadgets.db"

    migrate(SQLiteDatabase(path=widgets_path), _WIDGETS)
    migrate(SQLiteDatabase(path=gadgets_path), _GADGETS)

    # Each DB has only its own tables.
    assert "widgets" in _table_names(widgets_path)
    assert "gadgets" not in _table_names(widgets_path)
    assert "gadgets" in _table_names(gadgets_path)
    assert "widgets" not in _table_names(gadgets_path)

    # Each DB has the correct version stamp.
    assert _user_version(widgets_path) == 2
    assert _user_version(gadgets_path) == 1


def test_migrating_one_db_does_not_affect_another(tmp_path: Path) -> None:
    a_path = tmp_path / "a.db"
    b_path = tmp_path / "b.db"

    # Bring both to v1.
    migrate(SQLiteDatabase(path=a_path), _WIDGETS[:1])
    migrate(SQLiteDatabase(path=b_path), _WIDGETS[:1])

    assert _user_version(a_path) == 1
    assert _user_version(b_path) == 1

    # Advance only A to v2.
    migrate(SQLiteDatabase(path=a_path), _WIDGETS)

    assert _user_version(a_path) == 2
    assert _user_version(b_path) == 1  # B must still be at 1
