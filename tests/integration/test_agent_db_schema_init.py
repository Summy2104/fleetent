"""Integration tests for agent DB schema self-initialization.

Tests that ensure_schema() functions create the correct tables and indices,
and that _init_agent_db_schema() wires them all together correctly.
These tests use real SQLiteDatabase files and verify actual schema state.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase


def _db(tmp_path: Path) -> SQLiteDatabase:
    return SQLiteDatabase(path=tmp_path / "test.db")


def _table_names(db: SQLiteDatabase) -> set[str]:
    rows = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r["name"] for r in rows}


def _index_names(db: SQLiteDatabase) -> set[str]:
    rows = db.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    return {r["name"] for r in rows}


# ── traces ────────────────────────────────────────────────────────────────────

def test_traces_ensure_schema_creates_table(tmp_path: Path) -> None:
    from fleetent.observability.traces import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    assert "traces" in _table_names(db)


def test_traces_ensure_schema_creates_indices(tmp_path: Path) -> None:
    from fleetent.observability.traces import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    indices = _index_names(db)
    assert "idx_traces_run_id" in indices
    assert "idx_traces_user_ts" in indices
    assert "idx_traces_agent_ts" in indices
    assert "idx_traces_tenant_event_ts" in indices


def test_traces_ensure_schema_idempotent(tmp_path: Path) -> None:
    from fleetent.observability.traces import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    ensure_schema(db)
    assert "traces" in _table_names(db)


# ── memory ─────────────────────────────────────────────────────────────────────

def test_memory_ensure_schema_creates_table(tmp_path: Path) -> None:
    from fleetent.intelligence.memory.store import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    assert "memory_items" in _table_names(db)


def test_memory_ensure_schema_creates_indices(tmp_path: Path) -> None:
    from fleetent.intelligence.memory.store import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    indices = _index_names(db)
    assert "idx_memory_items_user_type" in indices
    assert "idx_memory_items_user_expires" in indices


def test_memory_ensure_schema_idempotent(tmp_path: Path) -> None:
    from fleetent.intelligence.memory.store import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    ensure_schema(db)
    assert "memory_items" in _table_names(db)


# ── reflection ─────────────────────────────────────────────────────────────────

def test_reflection_ensure_schema_creates_table(tmp_path: Path) -> None:
    from fleetent.intelligence.reflection import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    assert "reflection_reports" in _table_names(db)


def test_reflection_ensure_schema_creates_index(tmp_path: Path) -> None:
    from fleetent.intelligence.reflection import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    assert "idx_reflection_reports_scope_created" in _index_names(db)


def test_reflection_ensure_schema_idempotent(tmp_path: Path) -> None:
    from fleetent.intelligence.reflection import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    ensure_schema(db)
    assert "reflection_reports" in _table_names(db)


# ── knowledge base ─────────────────────────────────────────────────────────────

def test_kb_ensure_schema_creates_all_tables(tmp_path: Path) -> None:
    from fleetent.intelligence.knowledge_base.operations import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    tables = _table_names(db)
    assert "knowledge_bases" in tables
    assert "knowledge_documents" in tables
    assert "knowledge_chunks" in tables
    assert "knowledge_source_states" in tables


def test_kb_ensure_schema_creates_fts_table(tmp_path: Path) -> None:
    from fleetent.intelligence.knowledge_base.operations import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    # FTS5 virtual table name matches migration 008
    assert "knowledge_chunks_fts" in _table_names(db)


def test_kb_ensure_schema_idempotent(tmp_path: Path) -> None:
    from fleetent.intelligence.knowledge_base.operations import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    ensure_schema(db)
    assert "knowledge_chunks" in _table_names(db)


# ── _init_agent_db_schema ──────────────────────────────────────────────────────

def test_init_agent_db_schema_creates_all_agent_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "agent.db"
    database_url = f"sqlite:///{db_path}"

    from fleetent.runtime.agent_app import _init_agent_db_schema

    _init_agent_db_schema(database_url)

    db = SQLiteDatabase(path=db_path)
    tables = _table_names(db)
    assert "traces" in tables
    assert "memory_items" in tables
    assert "reflection_reports" in tables
    assert "knowledge_bases" in tables
    assert "knowledge_documents" in tables
    assert "knowledge_chunks" in tables
    assert "knowledge_chunks_fts" in tables
    assert "knowledge_source_states" in tables


def test_init_agent_db_schema_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.db"
    database_url = f"sqlite:///{db_path}"

    from fleetent.runtime.agent_app import _init_agent_db_schema

    _init_agent_db_schema(database_url)
    _init_agent_db_schema(database_url)
    assert SQLiteDatabase(path=db_path).execute(
        "SELECT name FROM sqlite_master WHERE name='traces'"
    ).fetchone() is not None
