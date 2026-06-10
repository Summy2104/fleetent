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
    from fleetent.memory.store import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    assert "memory_items" in _table_names(db)


def test_memory_ensure_schema_creates_indices(tmp_path: Path) -> None:
    from fleetent.memory.store import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    indices = _index_names(db)
    assert "idx_memory_items_user_type" in indices
    assert "idx_memory_items_user_expires" in indices


def test_memory_ensure_schema_idempotent(tmp_path: Path) -> None:
    from fleetent.memory.store import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    ensure_schema(db)
    assert "memory_items" in _table_names(db)


# ── reflection ─────────────────────────────────────────────────────────────────


def test_reflection_ensure_schema_creates_table(tmp_path: Path) -> None:
    from fleetent.reflection import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    assert "reflection_reports" in _table_names(db)


def test_reflection_ensure_schema_creates_index(tmp_path: Path) -> None:
    from fleetent.reflection import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    assert "idx_reflection_reports_scope_created" in _index_names(db)


def test_reflection_ensure_schema_idempotent(tmp_path: Path) -> None:
    from fleetent.reflection import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    ensure_schema(db)
    assert "reflection_reports" in _table_names(db)


# ── knowledge base ─────────────────────────────────────────────────────────────


def test_kb_ensure_schema_creates_all_tables(tmp_path: Path) -> None:
    from fleetent.knowledge_base.operations import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    tables = _table_names(db)
    assert "knowledge_bases" in tables
    assert "knowledge_documents" in tables
    assert "knowledge_chunks" in tables
    assert "knowledge_source_states" in tables


def test_kb_ensure_schema_creates_fts_table(tmp_path: Path) -> None:
    from fleetent.knowledge_base.operations import ensure_schema

    db = _db(tmp_path)
    ensure_schema(db)
    # FTS5 virtual table name matches migration 008
    assert "knowledge_chunks_fts" in _table_names(db)


def test_kb_ensure_schema_idempotent(tmp_path: Path) -> None:
    from fleetent.knowledge_base.operations import ensure_schema

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

    _init_agent_db_schema(database_url, agent_id="test-agent")

    # memory_items / schedule still land in the main agent db via ensure_schema (3b-3/4 pending).
    main_tables = _table_names(SQLiteDatabase(path=db_path))
    assert "memory_items" in main_tables
    # traces and reflection_reports are now Y-managed in agent_state.db (3b-2).
    assert "traces" not in main_tables
    assert "reflection_reports" not in main_tables
    # sessions never in main db (3b-1).
    assert "sessions" not in main_tables
    # KB tables must NOT be in the main db — Y-managed in tenant-scoped db.
    assert "knowledge_bases" not in main_tables
    assert "knowledge_documents" not in main_tables

    # KB tables land in default/kb.db via TenantRouter + migrate-on-open.
    kb_db_path = tmp_path / "default" / "kb.db"
    assert kb_db_path.exists()
    kb_tables = _table_names(SQLiteDatabase(path=kb_db_path))
    assert "knowledge_bases" in kb_tables
    assert "knowledge_documents" in kb_tables
    assert "knowledge_chunks" in kb_tables
    assert "knowledge_chunks_fts" in kb_tables
    assert "knowledge_source_states" in kb_tables

    # sessions + traces + reflection_reports land in per-agent agent_state.db (3b-1/3b-2).
    agent_state_db_path = tmp_path / "default" / "test-agent" / "agent_state.db"
    assert agent_state_db_path.exists()
    agent_tables = _table_names(SQLiteDatabase(path=agent_state_db_path))
    assert "sessions" in agent_tables
    assert "traces" in agent_tables
    assert "reflection_reports" in agent_tables


def test_init_agent_db_schema_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.db"
    database_url = f"sqlite:///{db_path}"

    from fleetent.runtime.agent_app import _init_agent_db_schema

    _init_agent_db_schema(database_url, agent_id="test-agent")
    _init_agent_db_schema(database_url, agent_id="test-agent")
    # traces is now in per-agent agent_state.db (3b-2), not the main db.
    agent_state_db_path = tmp_path / "default" / "test-agent" / "agent_state.db"
    assert (
        SQLiteDatabase(path=agent_state_db_path)
        .execute("SELECT name FROM sqlite_master WHERE name='traces'")
        .fetchone()
        is not None
    )
