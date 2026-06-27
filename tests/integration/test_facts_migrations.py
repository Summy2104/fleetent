"""Integration tests: facts / fact_edges / relation_clusters schema migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.schema_migrations import migrate
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS


def _open_migrated(tmp_path: Path) -> tuple[SQLiteDatabase, Path]:
    db_path = tmp_path / "agent_state.db"
    db = SQLiteDatabase(path=db_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db, db_path


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


def _fetch_all(db_path: Path, sql: str) -> list:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql).fetchall()
    conn.close()
    return rows


def test_facts_table_exists_after_migration(tmp_path: Path) -> None:
    _, db_path = _open_migrated(tmp_path)
    assert "memory_items" in _tables(db_path)
    assert "facts" not in _tables(db_path)


def test_fact_edges_table_exists_after_migration(tmp_path: Path) -> None:
    _, db_path = _open_migrated(tmp_path)
    assert "fact_edges" in _tables(db_path)


def test_relation_clusters_table_exists_after_migration(tmp_path: Path) -> None:
    _, db_path = _open_migrated(tmp_path)
    assert "relation_clusters" in _tables(db_path)


def test_facts_columns_complete(tmp_path: Path) -> None:
    _, db_path = _open_migrated(tmp_path)
    cols = _columns(db_path, "memory_items")
    expected = {
        "fact_id", "user_id", "subject", "relation", "object",
        "cardinality", "status", "access_count", "first_accessed_at",
        "last_accessed_at", "expires_at", "valid_until",
        "created_at", "updated_at", "source_turn", "statement", "scope",
    }
    assert expected <= cols


def test_relation_clusters_preset_rows_exist(tmp_path: Path) -> None:
    _, db_path = _open_migrated(tmp_path)
    rows = _fetch_all(db_path, "SELECT relation FROM relation_clusters ORDER BY relation")
    relations = {r["relation"] for r in rows}
    expected = {
        "is_role", "works_at", "located_in", "prefers_language",
        "speaks_language", "has_skill", "works_on_project",
        "prefers_tool", "interested_in",
    }
    assert expected <= relations


def test_user_version_increments(tmp_path: Path) -> None:
    _, db_path = _open_migrated(tmp_path)
    version = _user_version(db_path)
    # AGENT_STATE_MIGRATIONS[-1][0] is the last version number
    assert version == AGENT_STATE_MIGRATIONS[-1][0]


def test_idempotent_remigration(tmp_path: Path) -> None:
    db, db_path = _open_migrated(tmp_path)
    # Running migrate again on an already-migrated DB must not raise
    migrate(db, AGENT_STATE_MIGRATIONS)
    assert "memory_items" in _tables(db_path)
