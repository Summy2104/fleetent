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
        "knowledge_connector_status",
        "knowledge_connector_sync_history",
        "kb_entities",
        "kb_entity_mentions",
        "kb_relations",
    }
    assert "kb_extraction_runs" not in real_tables


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
        "extraction_enabled",
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
    assert _col_names(migrated_db, "knowledge_connector_status") == {
        "connector_id",
        "connector_type",
        "tenant_id",
        "kb_id",
        "last_status",
        "last_started_at",
        "last_finished_at",
        "last_summary_json",
        "last_error",
        "updated_at",
    }
    assert _col_names(migrated_db, "kb_entities") == {
        "id",
        "tenant_id",
        "kb_id",
        "entity_type",
        "name",
        "normalized_name",
        "metadata_json",
        "created_at",
        "updated_at",
    }
    assert _col_names(migrated_db, "kb_entity_mentions") == {
        "id",
        "entity_id",
        "tenant_id",
        "kb_id",
        "document_id",
        "chunk_id",
        "text",
        "confidence",
        "created_at",
    }
    assert _col_names(migrated_db, "kb_relations") == {
        "id",
        "tenant_id",
        "kb_id",
        "relation_type",
        "source_entity_id",
        "target_entity_id",
        "evidence_document_id",
        "evidence_chunk_id",
        "evidence_text",
        "confidence",
        "created_at",
    }


def test_kb_migrations_add_extraction_enabled_with_default_zero(tmp_path: Path) -> None:
    migrated_db = _build_migrations_db(tmp_path / "b")
    conn = sqlite3.connect(migrated_db)
    try:
        conn.execute(
            """
            INSERT INTO knowledge_bases (
                tenant_id, kb_id, created_at, description, archived_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("tenant-a", "support", "2026-06-29T00:00:00+00:00", "", None),
        )
        row = conn.execute(
            """
            SELECT extraction_enabled
            FROM knowledge_bases
            WHERE tenant_id = ? AND kb_id = ?
            """,
            ("tenant-a", "support"),
        ).fetchone()
    finally:
        conn.close()

    assert row == (0,)


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
