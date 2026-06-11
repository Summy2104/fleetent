"""Tests: KB MIGRATIONS via Y engine produce the expected tenant-scoped schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

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


def _build_migrations_db(tmp_path: Path) -> Path:
    from fleetent.db import SQLiteDatabase

    db_path = tmp_path / "migrated.db"
    migrate(SQLiteDatabase(path=db_path), KB_MIGRATIONS)
    return db_path


def test_kb_migrations_create_expected_tables(tmp_path: Path) -> None:
    migrated_db = _build_migrations_db(tmp_path / "b")
    migrated_tables = _table_names(migrated_db)
    real_tables = {t for t in migrated_tables if not t.startswith("knowledge_chunks_fts")}
    assert real_tables == {
        "knowledge_bases",
        "knowledge_documents",
        "knowledge_chunks",
        "knowledge_source_states",
    }


def test_kb_migrations_preserve_tenant_id_and_kb_id_columns(tmp_path: Path) -> None:
    migrated_db = _build_migrations_db(tmp_path)
    for table in ("knowledge_bases", "knowledge_documents", "knowledge_chunks"):
        cols = _col_names(migrated_db, table)
        assert "tenant_id" in cols, f"tenant_id missing from {table}"
        assert "kb_id" in cols, f"kb_id missing from {table}"


def test_kb_migrations_create_expected_columns(tmp_path: Path) -> None:
    migrated_db = _build_migrations_db(tmp_path / "b")

    assert _col_names(migrated_db, "knowledge_bases") == {
        "tenant_id",
        "kb_id",
        "created_at",
        "description",
        "archived_at",
    }
    assert _col_names(migrated_db, "knowledge_documents") == {
        "id",
        "tenant_id",
        "kb_id",
        "filename",
        "source",
        "source_url",
        "created_at",
        "archived_at",
    }
    assert _col_names(migrated_db, "knowledge_chunks") == {
        "id",
        "document_id",
        "tenant_id",
        "kb_id",
        "position",
        "content",
        "metadata_json",
        "created_at",
    }
    assert _col_names(migrated_db, "knowledge_source_states") == {
        "kb_id",
        "tenant_id",
        "document_id",
        "source_id",
        "source_path",
        "content_hash",
        "mtime_ns",
        "updated_at",
    }


def test_kb_migrations_create_expected_indices(tmp_path: Path) -> None:
    migrated_db = _build_migrations_db(tmp_path / "b")
    migrated_idx = _index_names(migrated_db)
    assert {
        "idx_knowledge_bases_archive",
        "idx_knowledge_documents_archive",
        "idx_knowledge_documents_scope",
        "idx_knowledge_chunks_document_position",
        "idx_knowledge_chunks_scope",
    } <= migrated_idx
