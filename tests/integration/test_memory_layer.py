import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fleetent import memory as memory_layer
from fleetent import vector_store
from fleetent.agent_config import AgentFile, default_models
from fleetent.db import SQLiteDatabase
from fleetent.memory import extraction, store
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate
from fleetent.vector_store import runtime as vector_runtime
from fleetent.vector_store.backend import SearchResult


@pytest.fixture(autouse=True)
def _reset_vector_runtime():
    agent = AgentFile(name="", version=0, models=default_models())
    vector_runtime._configure(agent)
    yield
    vector_runtime._configure(agent)


def test_memory_layer_public_api_exports_semantic_store_contract():
    assert memory_layer.MemoryItem
    assert callable(memory_layer.extract_and_update)
    assert callable(memory_layer.search)
    assert not hasattr(memory_layer, "load_memories")


def _patch_database(tmp_path, monkeypatch):
    db_path = tmp_path / "agent_state.db"
    db = SQLiteDatabase(path=db_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(store, "_state_db", db)
    monkeypatch.setattr(store, "_vector_backend", _TrackingBackend(), raising=False)
    monkeypatch.setattr(vector_store, "embed_text", AsyncMock(return_value=[0.1, 0.2, 0.3]))
    return db_path


class _TrackingBackend:
    def __init__(self, *, results: list[SearchResult] | None = None) -> None:
        self.results = results or []
        self.upserts: list[tuple[str, list[float], str]] = []
        self.deletes: list[tuple[str, str]] = []
        self.searches: list[tuple[list[float], str, int]] = []

    async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
        self.upserts.append((id, vector, namespace))

    async def search(
        self, vector: list[float], namespace: str, limit: int = 10
    ) -> list[SearchResult]:
        self.searches.append((vector, namespace, limit))
        return list(self.results)

    async def delete(self, id: str, namespace: str) -> None:
        self.deletes.append((id, namespace))

    async def clear_namespace(self, namespace: str) -> None:
        return None


def _patch_extraction(monkeypatch, content: str) -> AsyncMock:
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace()))
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )
    )
    client.chat.completions.create = create
    monkeypatch.setattr(extraction, "AsyncOpenAI", lambda **kwargs: client)
    return create


def _memory_rows(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM memory_items ORDER BY content")]


def _insert_memory_row(
    db_path,
    *,
    id: str,
    user_id: str = "alice",
    type: str = "identity",
    content: str,
    updated_at: str | None = None,
    expires_at: str | None = None,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    updated_at = updated_at or now
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memory_items (
                id, user_id, type, content, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (id, user_id, type, content, now, updated_at, expires_at),
        )


def _insert_memory_rows(db_path, rows: list[dict]) -> None:
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    params = [
        (
            r["id"],
            r.get("user_id", "alice"),
            r.get("type", "identity"),
            r["content"],
            now,
            r.get("updated_at") or now,
            r.get("expires_at"),
        )
        for r in rows
    ]
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO memory_items (
                id, user_id, type, content, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )


async def test_extract_and_update_ignores_ignore_actions(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    _patch_extraction(
        monkeypatch,
        """[{"action": "ignore", "reason": "one-off request"}]""",
    )

    await memory_layer.extract_and_update(
        "alice", [{"role": "user", "content": "Use bullets only this time"}]
    )

    assert _memory_rows(db_path) == []


async def test_extract_and_update_ignores_invalid_memory_type(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    _patch_extraction(
        monkeypatch,
        """[{"action": "create", "type": "project", "content": "User works on billing"}]""",
    )

    await memory_layer.extract_and_update("alice", [{"role": "user", "content": "facts"}])

    assert _memory_rows(db_path) == []


async def test_extract_and_update_ignores_delete_target_outside_current_snapshot(
    tmp_path, monkeypatch
):
    db_path = _patch_database(tmp_path, monkeypatch)
    backend = _TrackingBackend()
    vector_delete = AsyncMock()
    monkeypatch.setattr(store, "_vector_backend", backend, raising=False)
    monkeypatch.setattr(vector_store, "delete", vector_delete)
    expired = (datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)).isoformat()
    _insert_memory_row(
        db_path,
        id="bob-memory",
        user_id="bob",
        content="Bob memory",
    )
    _insert_memory_row(
        db_path,
        id="expired-context",
        type="context",
        content="Expired context memory",
        expires_at=expired,
    )
    _patch_extraction(
        monkeypatch,
        """
        [
          {"action": "delete", "target_id": "bob-memory"},
          {"action": "delete", "target_id": "expired-context"}
        ]
        """,
    )

    await memory_layer.extract_and_update("alice", [{"role": "user", "content": "forget"}])

    assert {row["id"] for row in _memory_rows(db_path)} == {"bob-memory", "expired-context"}
    assert backend.deletes == []
    vector_delete.assert_not_awaited()


async def test_extract_and_update_ignores_invalid_mutation_outputs(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    backend = _TrackingBackend()
    vector_upsert = AsyncMock()
    vector_delete = AsyncMock()
    monkeypatch.setattr(store, "_vector_backend", backend, raising=False)
    monkeypatch.setattr(vector_store, "upsert", vector_upsert)
    monkeypatch.setattr(vector_store, "delete", vector_delete)
    _insert_memory_row(
        db_path,
        id="mem-identity",
        content="User is a backend engineer",
    )
    _patch_extraction(
        monkeypatch,
        """
        [
          {"action": "archive", "type": "identity", "content": "Unknown action"},
          {"action": "create", "type": "project", "content": "Invalid type"},
          {"action": "create", "type": "identity", "content": "   "},
          {
            "action": "update",
            "type": "identity",
            "content": "Missing target id"
          },
          {
            "action": "update",
            "target_id": "missing",
            "type": "identity",
            "content": "Invalid target id"
          },
          {"action": "delete"}
        ]
        """,
    )

    await memory_layer.extract_and_update("alice", [{"role": "user", "content": "facts"}])

    [row] = _memory_rows(db_path)
    assert row["id"] == "mem-identity"
    assert row["content"] == "User is a backend engineer"
    assert backend.upserts == []
    assert backend.deletes == []
    vector_upsert.assert_not_awaited()
    vector_delete.assert_not_awaited()


async def test_extract_and_update_ignores_invalid_json_without_mutation(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    _insert_memory_row(
        db_path,
        id="mem-identity",
        content="User is a backend engineer",
    )
    _patch_extraction(monkeypatch, "{not json")

    await memory_layer.extract_and_update("alice", [{"role": "user", "content": "facts"}])

    [row] = _memory_rows(db_path)
    assert row["content"] == "User is a backend engineer"


async def test_extract_and_update_ignores_one_off_preference_requests(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    _patch_extraction(monkeypatch, """[{"action": "ignore", "reason": "one-time request"}]""")

    await memory_layer.extract_and_update(
        "alice", [{"role": "user", "content": "Use a table for this answer only"}]
    )

    assert _memory_rows(db_path) == []


async def test_public_memory_mutations_use_injected_vector_backend(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    backend = _TrackingBackend()
    embed_text = AsyncMock(return_value=[0.9, 0.1, 0.3])
    vector_upsert = AsyncMock()
    vector_delete = AsyncMock()
    monkeypatch.setattr(store, "_vector_backend", backend, raising=False)
    monkeypatch.setattr(vector_store, "embed_text", embed_text)
    monkeypatch.setattr(vector_store, "upsert", vector_upsert)
    monkeypatch.setattr(vector_store, "delete", vector_delete)
    _insert_memory_row(
        db_path,
        id="mem-1",
        type="context",
        content="User is working on billing",
        expires_at=(datetime.now(UTC).replace(microsecond=0) + timedelta(days=1)).isoformat(),
    )

    await memory_layer.update_user_memory_content("alice", "mem-1", "User is working on payments")
    await memory_layer.mark_user_memory_stale("alice", "mem-1")
    await memory_layer.delete_user_memory("alice", "mem-1")

    embed_text.assert_awaited_once_with("User is working on payments")
    assert backend.upserts == [("mem-1", [0.9, 0.1, 0.3], "mem:alice")]
    assert backend.deletes == [("mem-1", "mem:alice"), ("mem-1", "mem:alice")]
    vector_upsert.assert_not_awaited()
    vector_delete.assert_not_awaited()
