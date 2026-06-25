"""Unit tests for agent_memory public API — no real DB, all mocked."""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, MagicMock, patch


def test_create_agent_memory_has_no_scope_parameters() -> None:
    import inspect

    module = importlib.import_module("fleetent.memory.agent_memory")
    func = module.create_agent_memory
    sig = inspect.signature(func)
    params = set(sig.parameters)
    assert "scope_type" not in params, "create_agent_memory must not have scope_type parameter"
    assert "scope_id" not in params, "create_agent_memory must not have scope_id parameter"


def test_search_agent_memory_has_no_scope_parameters() -> None:
    import inspect

    module = importlib.import_module("fleetent.memory.agent_memory")
    func = module.search_agent_memory
    sig = inspect.signature(func)
    params = set(sig.parameters)
    assert "scope_type" not in params, "search_agent_memory must not have scope_type"
    assert "scope_id" not in params, "search_agent_memory must not have scope_id"


def test_list_agent_memory_has_no_scope_parameters() -> None:
    import inspect

    module = importlib.import_module("fleetent.memory.agent_memory")
    func = module.list_agent_memory
    sig = inspect.signature(func)
    params = set(sig.parameters)
    assert "scope_type" not in params, "list_agent_memory must not have scope_type"
    assert "scope_id" not in params, "list_agent_memory must not have scope_id"


def test_iter_indexable_agent_memories_has_no_scope_parameters() -> None:
    import inspect

    module = importlib.import_module("fleetent.memory.agent_memory")
    func = module.iter_indexable_agent_memories
    sig = inspect.signature(func)
    params = set(sig.parameters)
    assert "scope_type" not in params, "iter_indexable_agent_memories must not have scope_type"
    assert "scope_id" not in params, "iter_indexable_agent_memories must not have scope_id"


def test_agent_memory_item_has_no_scope_fields() -> None:
    import dataclasses

    from fleetent.memory.models import AgentMemoryItem

    field_names = {f.name for f in dataclasses.fields(AgentMemoryItem)}
    assert "scope_type" not in field_names, "AgentMemoryItem must not have scope_type field"
    assert "scope_id" not in field_names, "AgentMemoryItem must not have scope_id field"


def test_set_agent_memory_db_function_exists() -> None:
    module = importlib.import_module("fleetent.memory.agent_memory")
    assert hasattr(module, "set_agent_memory_db"), "set_agent_memory_db must exist"


async def test_create_agent_memory_reads_from_injected_db() -> None:
    module = importlib.import_module("fleetent.memory.agent_memory")

    mock_db = MagicMock()
    mock_db.execute.return_value = mock_db
    mock_backend = AsyncMock()

    mock_embed = AsyncMock(return_value=[0.1, 0.2])
    mock_upsert = AsyncMock()

    with (
        patch.object(module, "_agent_memory_db", mock_db),
        patch.object(module, "_vector_backend", mock_backend),
        patch("fleetent.vector_store.embed_text", mock_embed),
        patch.object(mock_backend, "upsert", mock_upsert),
    ):
        item = await module.create_agent_memory(
            type="context",
            content="agent memory content",
            created_by="user-1",
        )

    assert item.content == "agent memory content"
    assert item.type == "context"
    assert not hasattr(item, "scope_type")
    assert not hasattr(item, "scope_id")
    mock_db.execute.assert_called()
