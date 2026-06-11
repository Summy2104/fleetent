"""Integration tests for boot-path KB and memory schema routing.

Verifies that _init_agent_db_schema routes KB and memory schema setup through the
TenantRouter + migrate-on-open (AGENT_STATE_MIGRATIONS), not via ensure_schema into
the main db.
"""

from __future__ import annotations

import sqlite3


def _tables_in(db_path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }


def test_kb_schema_established_in_tenant_scoped_db(tmp_path) -> None:
    """KB tables land in default/kb.db, not in the main agent db."""
    from fleetent.runtime.agent_app import _init_agent_db_schema

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _init_agent_db_schema(data_dir, agent_id="test-agent")

    kb_db_path = data_dir / "default" / "kb.db"
    assert kb_db_path.exists(), "router must create data/default/kb.db"

    tables = _tables_in(kb_db_path)
    assert "knowledge_bases" in tables
    assert "knowledge_documents" in tables
    assert "knowledge_chunks" in tables
    assert "knowledge_source_states" in tables


def test_kb_tables_absent_from_main_agent_db(tmp_path) -> None:
    """KB tables must NOT be in agent_state.db; they land in the tenant kb.db."""
    from fleetent.runtime.agent_app import _init_agent_db_schema

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _init_agent_db_schema(data_dir, agent_id="test-agent")

    agent_state_path = data_dir / "default" / "test-agent" / "agent_state.db"
    assert agent_state_path.exists()
    tables = _tables_in(agent_state_path)
    assert "knowledge_bases" not in tables, "KB tables must not pollute agent_state.db"
    assert "knowledge_documents" not in tables
    assert "knowledge_chunks" not in tables
    assert not (data_dir / "fleetent.db").exists(), "fleetent.db must not be created"


def test_memory_items_is_y_managed_in_agent_state_db(tmp_path) -> None:
    """memory_items is Y-managed in agent_state.db (3b-3); no standalone fleetent.db."""
    from fleetent.runtime.agent_app import _init_agent_db_schema

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _init_agent_db_schema(data_dir, agent_id="test-agent")

    agent_state_path = data_dir / "default" / "test-agent" / "agent_state.db"
    assert agent_state_path.exists()
    tables = _tables_in(agent_state_path)
    # memory_items, traces, and reflection_reports are all Y-managed in agent_state.db.
    assert "memory_items" in tables
    assert "traces" in tables
    assert "reflection_reports" in tables
    assert not (data_dir / "fleetent.db").exists(), "fleetent.db must not be created"


def test_traces_and_reflection_land_in_agent_state_db(tmp_path) -> None:
    """traces + reflection_reports + memory_items all Y-managed in agent_state.db (3b-2/3b-3)."""
    from fleetent.runtime.agent_app import _init_agent_db_schema

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _init_agent_db_schema(data_dir, agent_id="test-agent")

    agent_state_path = data_dir / "default" / "test-agent" / "agent_state.db"
    assert agent_state_path.exists()
    agent_tables = _tables_in(agent_state_path)
    assert "traces" in agent_tables
    assert "reflection_reports" in agent_tables
    assert "sessions" in agent_tables
    assert "memory_items" in agent_tables


async def test_agent_boot_search_reads_only_boot_tenant_kb(tmp_path, monkeypatch) -> None:
    from fleetent.knowledge_base import runtime
    from fleetent.runtime.agent_app import _init_agent_db_schema
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    async def embed_text(text: str) -> list[float]:
        return [1.0, 0.0]

    monkeypatch.setattr(runtime.vector_store, "embed_text", embed_text)

    _init_agent_db_schema(data_dir, agent_id="test-agent", tenant_id="tenant-a")

    await runtime.ingest_text(
        filename="guide.txt",
        content="tenant scoped handbook",
        tenant_id="tenant-a",
        kb_id="global",
    )

    tenant_a_results = await runtime.search(
        "handbook",
        tenant_id="tenant-a",
        kb_ids=["global"],
        limit=5,
    )
    assert [chunk.tenant_id for chunk in tenant_a_results] == ["tenant-a"]
    assert (data_dir / "tenant-a" / "kb_vectors.db").exists()

    router = TenantRouter(SQLiteTenantBackend(data_dir=data_dir))
    tenant_b_scope = router.tenant_scope("tenant-b")
    runtime.set_database(tenant_b_scope.open_kb_db([]))
    runtime.set_vector_backend(tenant_b_scope.kb_vector_backend)

    tenant_b_results = await runtime.search(
        "handbook",
        tenant_id="tenant-b",
        kb_ids=["global"],
        limit=5,
    )
    assert tenant_b_results == []
