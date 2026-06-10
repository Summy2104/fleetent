"""Integration tests for boot-path KB schema routing.

Verifies that _init_agent_db_schema routes KB schema setup through the
TenantRouter + migrate-on-open, not through kb_ops.ensure_schema into the main db.
Other agent-side stores (traces, memory, reflection) continue using ensure_schema.
"""

from __future__ import annotations

import sqlite3


def _tables_in(db_path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }


def test_kb_schema_established_in_tenant_scoped_db(tmp_path) -> None:
    """KB tables land in default/kb.db, not in the main agent db."""
    from fleetent.runtime.agent_app import _init_agent_db_schema

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_url = f"sqlite:///{data_dir / 'fleetent.db'}"

    _init_agent_db_schema(db_url, agent_id="test-agent")

    kb_db_path = data_dir / "default" / "kb.db"
    assert kb_db_path.exists(), "router must create data/default/kb.db"

    tables = _tables_in(kb_db_path)
    assert "knowledge_bases" in tables
    assert "knowledge_documents" in tables
    assert "knowledge_chunks" in tables
    assert "knowledge_source_states" in tables


def test_kb_tables_absent_from_main_agent_db(tmp_path) -> None:
    """KB tables must NOT be in the main fleetent.db after boot."""
    from fleetent.runtime.agent_app import _init_agent_db_schema

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_url = f"sqlite:///{data_dir / 'fleetent.db'}"

    _init_agent_db_schema(db_url, agent_id="test-agent")

    main_db_path = data_dir / "fleetent.db"
    if main_db_path.exists():
        tables = _tables_in(main_db_path)
        assert "knowledge_bases" not in tables, "KB tables must not pollute the main agent db"
        assert "knowledge_documents" not in tables
        assert "knowledge_chunks" not in tables


def test_other_stores_still_use_ensure_schema(tmp_path) -> None:
    """traces, memory_items, reflection tables stay in the main db via ensure_schema."""
    from fleetent.runtime.agent_app import _init_agent_db_schema

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_url = f"sqlite:///{data_dir / 'fleetent.db'}"

    _init_agent_db_schema(db_url, agent_id="test-agent")

    main_db_path = data_dir / "fleetent.db"
    assert main_db_path.exists()
    tables = _tables_in(main_db_path)
    assert "traces" in tables
    assert "memory_items" in tables
    assert "reflection_reports" in tables
