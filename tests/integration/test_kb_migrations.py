"""Tests: KB MIGRATIONS via Y engine produce schema equivalent to ensure_schema.

After running the KB MIGRATIONS list through the Y engine on an empty DB, the
resulting table/column/index set must be equivalent to what ensure_schema()
previously produced, including tenant_id and kb_id columns.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fleetent.db import SQLiteDatabase
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.schema_migrations import migrate


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


def _index_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        )
    }
    conn.close()
    return names


def _build_ensure_schema_db(tmp_path: Path) -> Path:
    from fleetent.knowledge_base.operations import ensure_schema

    db_path = tmp_path / "ensure.db"
    ensure_schema(SQLiteDatabase(path=db_path))
    return db_path


def _build_migrations_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "migrated.db"
    migrate(SQLiteDatabase(path=db_path), KB_MIGRATIONS)
    return db_path


def test_kb_migrations_create_same_tables_as_ensure_schema(tmp_path: Path) -> None:
    ensure_db = _build_ensure_schema_db(tmp_path / "a")
    migrated_db = _build_migrations_db(tmp_path / "b")

    ensure_tables = _table_names(ensure_db)
    migrated_tables = _table_names(migrated_db)

    # Filter out FTS shadow tables (fts_*) for comparison; compare real tables.
    real_ensure = {t for t in ensure_tables if not t.startswith("knowledge_chunks_fts")}
    real_migrated = {t for t in migrated_tables if not t.startswith("knowledge_chunks_fts")}

    assert real_migrated == real_ensure, (
        f"Table set mismatch:\n  missing={real_ensure - real_migrated}\n"
        f"  extra={real_migrated - real_ensure}"
    )


def test_kb_migrations_preserve_tenant_id_and_kb_id_columns(tmp_path: Path) -> None:
    migrated_db = _build_migrations_db(tmp_path)
    for table in ("knowledge_bases", "knowledge_documents", "knowledge_chunks"):
        cols = _col_names(migrated_db, table)
        assert "tenant_id" in cols, f"tenant_id missing from {table}"
        assert "kb_id" in cols, f"kb_id missing from {table}"


def test_kb_migrations_create_same_columns_as_ensure_schema(tmp_path: Path) -> None:
    ensure_db = _build_ensure_schema_db(tmp_path / "a")
    migrated_db = _build_migrations_db(tmp_path / "b")

    tables = {"knowledge_bases", "knowledge_documents", "knowledge_chunks", "knowledge_source_states"}
    for table in tables:
        ensure_cols = _col_names(ensure_db, table)
        migrated_cols = _col_names(migrated_db, table)
        assert migrated_cols == ensure_cols, (
            f"Column mismatch in {table}:\n"
            f"  missing={ensure_cols - migrated_cols}\n"
            f"  extra={migrated_cols - ensure_cols}"
        )


def test_kb_migrations_create_same_indices_as_ensure_schema(tmp_path: Path) -> None:
    ensure_db = _build_ensure_schema_db(tmp_path / "a")
    migrated_db = _build_migrations_db(tmp_path / "b")

    ensure_idx = _index_names(ensure_db)
    migrated_idx = _index_names(migrated_db)

    assert migrated_idx == ensure_idx, (
        f"Index set mismatch:\n  missing={ensure_idx - migrated_idx}\n"
        f"  extra={migrated_idx - ensure_idx}"
    )
