from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

from fleetent import vector_store
from fleetent.memory import agent_memory, facts_commit, facts_store
from fleetent.memory.facts_models import Fact
from fleetent.runtime.agent_app import _init_agent_db_schema


def _make_fact(fact_id: str, user_id: str, subject: str, relation: str, object_: str) -> Fact:
    now = datetime(2026, 6, 11, tzinfo=UTC)
    return Fact(
        fact_id=fact_id,
        user_id=user_id,
        subject=subject,
        relation=relation,
        object=object_,
        cardinality="multi",
        status="active",
        access_count=0,
        first_accessed_at=None,
        last_accessed_at=None,
        expires_at=None,
        valid_until=None,
        created_at=now,
        updated_at=now,
        source_turn=None,
    )


def _vector_rows(db_path: Path) -> list[tuple[str, str]]:
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT namespace, id FROM vector_items ORDER BY namespace ASC, id ASC"
        ).fetchall()


def test_agent_app_calls_memory_set_vector_backend() -> None:
    import fleetent.runtime.agent_app as agent_app_module

    src = inspect.getsource(agent_app_module._init_agent_db_schema)
    # user-memory-v2: facts_store.set_facts_db wires both the facts DB and vector backend.
    assert "facts_store.set_facts_db" in src, (
        "_init_agent_db_schema must call facts_store.set_facts_db(agent_state_db, agent_scope.vector_backend)"
    )


def test_memory_modules_do_not_bypass_injected_vector_backend() -> None:
    # user-memory-v2: extraction/maintenance/operations replaced by facts_* modules.
    import fleetent.memory.facts_commit as facts_commit_module
    import fleetent.memory.facts_lifecycle as facts_lifecycle_module
    import fleetent.memory.facts_search as facts_search_module

    disallowed_calls = ("vector_store.search(", "vector_store.upsert(", "vector_store.delete(")
    for module in (facts_commit_module, facts_lifecycle_module, facts_search_module):
        source = inspect.getsource(module)
        for disallowed in disallowed_calls:
            assert disallowed not in source, (
                f"{module.__name__} must use the injected vector backend; found {disallowed}"
            )


async def test_agent_boot_routes_memory_vectors_to_agent_scoped_backend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(vector_store, "embed_text", AsyncMock(return_value=[1.0, 0.0]))
    monkeypatch.setattr(vector_store, "upsert", AsyncMock())
    monkeypatch.setattr(vector_store, "delete", AsyncMock())

    _init_agent_db_schema(data_dir, agent_id="agent-a", tenant_id="default")
    fact_a = _make_fact("mem-a", "alice", "alice", "name", "Agent A")
    facts_store.insert_fact(fact_a)
    await facts_commit.sync_vectors(
        "alice",
        new_active=[fact_a],
        superseded_ids=[],
        vector_backend=facts_store._facts_vector(),
    )

    _init_agent_db_schema(data_dir, agent_id="agent-b", tenant_id="default")
    fact_b = _make_fact("mem-b", "alice", "alice", "name", "Agent B")
    facts_store.insert_fact(fact_b)
    await facts_commit.sync_vectors(
        "alice",
        new_active=[fact_b],
        superseded_ids=[],
        vector_backend=facts_store._facts_vector(),
    )

    agent_a_vectors_db = (
        tmp_path / "tenants" / "default" / "agents" / "agent-a" / "data" / "agent_vectors.db"
    )
    agent_b_vectors_db = (
        tmp_path / "tenants" / "default" / "agents" / "agent-b" / "data" / "agent_vectors.db"
    )
    assert _vector_rows(agent_a_vectors_db) == [("mem:alice", "mem-a")]
    assert _vector_rows(agent_b_vectors_db) == [("mem:alice", "mem-b")]
    vector_store.upsert.assert_not_awaited()


async def test_shared_agent_vector_store_keeps_user_and_agent_memory_isolated(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    vectors = {
        "alice name User": [1.0, 0.0],
        "user query": [1.0, 0.0],
        "Agent preference stored": [0.0, 1.0],
        "agent query": [0.0, 1.0],
    }
    monkeypatch.setattr(
        vector_store,
        "embed_text",
        AsyncMock(side_effect=lambda text: vectors[text]),
    )
    monkeypatch.setattr(vector_store, "upsert", AsyncMock())
    monkeypatch.setattr(vector_store, "delete", AsyncMock())

    _init_agent_db_schema(data_dir, agent_id="agent-a", tenant_id="default")

    agent_root = tmp_path / "tenants" / "default" / "agents" / "agent-a" / "data"
    fact = _make_fact("mem-a", "alice", "alice", "name", "User")
    facts_store.insert_fact(fact)
    await facts_commit.sync_vectors(
        "alice",
        new_active=[fact],
        superseded_ids=[],
        vector_backend=facts_store._facts_vector(),
    )
    agent_item = await agent_memory.create_agent_memory(
        type="preference",
        content="Agent preference stored",
        created_by="system",
    )

    vector_rows = _vector_rows(agent_root / "agent_vectors.db")
    assert {namespace for namespace, _ in vector_rows} == {"mem:alice", "agentmem:"}
    retired_vectors_db = agent_root / ("agent_memory" + "_vectors.db")
    assert not retired_vectors_db.exists()

    agent_results = await agent_memory.search_agent_memory("agent query")
    assert [item.id for item in agent_results] == [agent_item.id]
    assert "mem-a" not in {item.id for item in await agent_memory.search_agent_memory("user query")}
