from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock

from fleetent import memory as memory_layer
from fleetent import vector_store
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
    import fleetent.memory.search as search_module

    disallowed_calls = ("vector_store.search(", "vector_store.upsert(", "vector_store.delete(")
    for module in (
        search_module,
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
