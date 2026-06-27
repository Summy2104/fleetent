from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock

from fleetent import memory as memory_layer
from fleetent import vector_store
from fleetent.memory import agent_memory
from fleetent.runtime.agent_app import _init_agent_db_schema


def _insert_memory_row(
    db_path: Path,
    *,
    id: str,
    user_id: str,
    content: str,
    type: str = "identity",
) -> None:
    now = "2026-06-11T00:00:00+00:00"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memory_items (
                id, user_id, type, content, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (id, user_id, type, content, now, now, None),
        )


def _vector_rows(db_path: Path) -> list[tuple[str, str]]:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT namespace, id FROM vector_items ORDER BY namespace ASC, id ASC"
        ).fetchall()


def test_agent_app_calls_memory_set_vector_backend() -> None:
    import fleetent.runtime.agent_app as agent_app_module

    src = inspect.getsource(agent_app_module._init_agent_db_schema)
    assert "memory_store.set_vector_backend" in src, (
        "_init_agent_db_schema must call memory_store.set_vector_backend("
        "agent_scope.vector_backend)"
    )


def test_memory_modules_do_not_bypass_injected_vector_backend() -> None:
    import fleetent.memory.extraction as extraction_module
    import fleetent.memory.maintenance as maintenance_module
    import fleetent.memory.operations as operations_module

    disallowed_calls = ("vector_store.search(", "vector_store.upsert(", "vector_store.delete(")
    for module in (
        operations_module,
        extraction_module,
        maintenance_module,
    ):
        source = inspect.getsource(module)
        for disallowed in disallowed_calls:
            assert disallowed not in source, (
                f"{module.__name__} must use the injected memory vector backend; found {disallowed}"
            )


async def test_agent_boot_routes_memory_vectors_to_agent_scoped_backend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    embed_text = AsyncMock(
        side_effect=lambda text: [1.0, 0.0] if text == "Agent A updated" else [0.0, 1.0]
    )
    monkeypatch.setattr(vector_store, "embed_text", embed_text)
    monkeypatch.setattr(vector_store, "upsert", AsyncMock())
    monkeypatch.setattr(vector_store, "delete", AsyncMock())

    _init_agent_db_schema(
        data_dir,
        agent_id="agent-a",
        tenant_id="default",
    )
    agent_a_state_db = (
        tmp_path / "tenants" / "default" / "agents" / "agent-a" / "data" / "agent_state.db"
    )
    _insert_memory_row(agent_a_state_db, id="mem-a", user_id="alice", content="Agent A original")
    await memory_layer.update_user_memory_content("alice", "mem-a", "Agent A updated")

    _init_agent_db_schema(
        data_dir,
        agent_id="agent-b",
        tenant_id="default",
    )
    agent_b_state_db = (
        tmp_path / "tenants" / "default" / "agents" / "agent-b" / "data" / "agent_state.db"
    )
    _insert_memory_row(agent_b_state_db, id="mem-b", user_id="alice", content="Agent B original")
    await memory_layer.update_user_memory_content("alice", "mem-b", "Agent B updated")

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
        "User memory stored": [1.0, 0.0],
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
    state_db = agent_root / "agent_state.db"
    _insert_memory_row(state_db, id="mem-a", user_id="alice", content="Original")
    await memory_layer.update_user_memory_content("alice", "mem-a", "User memory stored")
    agent_item = await agent_memory.create_agent_memory(
        type="preference",
        content="Agent preference stored",
        created_by="system",
    )

    vector_rows = _vector_rows(agent_root / "agent_vectors.db")
    assert {namespace for namespace, _ in vector_rows} == {"mem:alice", "agentmem:"}
    retired_vectors_db = agent_root / ("agent_memory" + "_vectors.db")
    assert not retired_vectors_db.exists()

    # Free-text user-memory search was retired by user-memory-v2: memory.search()
    # now returns [] (facts live in a separate store), so the old user-side
    # retrieval assertion no longer applies. Storage-layer isolation is already
    # proven by the vector namespaces above; here we additionally verify the live
    # agent-memory retrieval stays within its own "agentmem:" namespace and never
    # surfaces the user-memory row.
    agent_results = await agent_memory.search_agent_memory("agent query")
    assert [item.id for item in agent_results] == [agent_item.id]
    assert "mem-a" not in {item.id for item in await agent_memory.search_agent_memory("user query")}
