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


async def test_extract_and_update_writes_create_actions(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    _patch_extraction(
        monkeypatch,
        """
        [
          {"action": "create", "type": "identity", "content": "User is a backend engineer"},
          {"action": "create", "type": "preferences", "content": "User prefers concise replies"}
        ]
        """,
    )

    await memory_layer.extract_and_update(
        "alice", [{"role": "user", "content": "I am a backend engineer"}]
    )

    rows = _memory_rows(db_path)
    assert [row["content"] for row in rows] == [
        "User is a backend engineer",
        "User prefers concise replies",
    ]
    assert {row["user_id"] for row in rows} == {"alice"}


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


async def test_extract_and_update_applies_type_ttl_rules(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    _patch_extraction(
        monkeypatch,
        """
        [
          {"action": "create", "type": "identity", "content": "User is a backend engineer"},
          {"action": "create", "type": "preferences", "content": "User prefers Chinese"},
          {"action": "create", "type": "context", "content": "User is working on billing"}
        ]
        """,
    )
    before = datetime.now(UTC).replace(microsecond=0) + timedelta(days=30)

    await memory_layer.extract_and_update("alice", [{"role": "user", "content": "facts"}])

    after = datetime.now(UTC).replace(microsecond=0) + timedelta(days=30)
    rows = {row["type"]: row for row in _memory_rows(db_path)}
    assert rows["identity"]["expires_at"] is None
    assert rows["preferences"]["expires_at"] is None
    context_expires = datetime.fromisoformat(rows["context"]["expires_at"])
    assert before <= context_expires <= after


async def test_extract_and_update_ignores_invalid_memory_type(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    _patch_extraction(
        monkeypatch,
        """[{"action": "create", "type": "project", "content": "User works on billing"}]""",
    )

    await memory_layer.extract_and_update("alice", [{"role": "user", "content": "facts"}])

    assert _memory_rows(db_path) == []


async def test_extract_and_update_upserts_created_memory_to_vector_store(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    backend = _TrackingBackend()
    embed_text = AsyncMock(return_value=[0.4, 0.5, 0.6])
    vector_upsert = AsyncMock()
    monkeypatch.setattr(store, "_vector_backend", backend, raising=False)
    monkeypatch.setattr(vector_store, "embed_text", embed_text)
    monkeypatch.setattr(vector_store, "upsert", vector_upsert)
    _patch_extraction(
        monkeypatch,
        """[{"action": "create", "type": "identity", "content": "User is a backend engineer"}]""",
    )

    await memory_layer.extract_and_update(
        "alice", [{"role": "user", "content": "I am a backend engineer"}]
    )

    [row] = _memory_rows(db_path)
    embed_text.assert_awaited_once_with("User is a backend engineer")
    assert backend.upserts == [(row["id"], [0.4, 0.5, 0.6], vector_store.memory_namespace("alice"))]
    vector_upsert.assert_not_awaited()


async def test_extract_and_update_includes_current_user_memory_snapshot(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    _insert_memory_row(
        db_path,
        id="alice-identity",
        content="User is a backend engineer",
    )
    _insert_memory_row(
        db_path,
        id="alice-preference",
        type="preferences",
        content="User prefers concise replies",
    )
    _insert_memory_row(
        db_path,
        id="alice-context",
        type="context",
        content="User is working on billing",
        expires_at=(datetime.now(UTC).replace(microsecond=0) + timedelta(days=1)).isoformat(),
    )
    _insert_memory_row(
        db_path,
        id="bob-identity",
        user_id="bob",
        content="Bob likes unrelated data",
    )
    create = _patch_extraction(monkeypatch, "[]")

    await memory_layer.extract_and_update(
        "alice", [{"role": "user", "content": "I now work on payments"}]
    )

    user_message = create.await_args.kwargs["messages"][1]["content"]
    assert "Existing memory snapshot:" in user_message
    assert "alice-identity" in user_message
    assert "User is a backend engineer" in user_message
    assert "alice-preference" in user_message
    assert "User prefers concise replies" in user_message
    assert "alice-context" in user_message
    assert "User is working on billing" in user_message
    assert "bob-identity" not in user_message
    assert "Bob likes unrelated data" not in user_message


async def test_extract_and_update_limits_snapshot_and_excludes_expired_context(
    tmp_path, monkeypatch
):
    db_path = _patch_database(tmp_path, monkeypatch)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    context_expiry = (datetime.now(UTC).replace(microsecond=0) + timedelta(days=1)).isoformat()
    _insert_memory_rows(
        db_path,
        [
            {
                "id": f"identity-{i}",
                "content": f"identity memory {i}",
                "updated_at": (base + timedelta(minutes=i)).isoformat(),
            }
            for i in range(25)
        ]
        + [
            {
                "id": f"preference-{i}",
                "type": "preferences",
                "content": f"preference memory {i}",
                "updated_at": (base + timedelta(minutes=i)).isoformat(),
            }
            for i in range(35)
        ]
        + [
            {
                "id": f"context-{i}",
                "type": "context",
                "content": f"context memory {i}",
                "updated_at": (base + timedelta(minutes=i)).isoformat(),
                "expires_at": context_expiry,
            }
            for i in range(25)
        ]
        + [
            {
                "id": "expired-context",
                "type": "context",
                "content": "expired context memory",
                "expires_at": (
                    datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)
                ).isoformat(),
            }
        ],
    )
    create = _patch_extraction(monkeypatch, "[]")

    await memory_layer.extract_and_update("alice", [{"role": "user", "content": "facts"}])

    user_message = create.await_args.kwargs["messages"][1]["content"]
    assert "identity-24" in user_message
    assert "identity-5" in user_message
    assert "identity-4" not in user_message
    assert "preference-34" in user_message
    assert "preference-5" in user_message
    assert "preference-4" not in user_message
    assert "context-24" in user_message
    assert "context-5" in user_message
    assert "context-4" not in user_message
    assert "expired-context" not in user_message
    assert "expired context memory" not in user_message


async def test_extract_and_update_updates_existing_memory_content_and_timestamp(
    tmp_path, monkeypatch
):
    db_path = _patch_database(tmp_path, monkeypatch)
    old_updated_at = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    _insert_memory_row(
        db_path,
        id="mem-identity",
        content="User is a backend engineer",
        updated_at=old_updated_at,
    )
    _patch_extraction(
        monkeypatch,
        """
        [
          {
            "action": "update",
            "target_id": "mem-identity",
            "type": "identity",
            "content": "User is a platform engineer"
          }
        ]
        """,
    )

    await memory_layer.extract_and_update(
        "alice", [{"role": "user", "content": "I am a platform engineer now"}]
    )

    [row] = _memory_rows(db_path)
    assert row["id"] == "mem-identity"
    assert row["content"] == "User is a platform engineer"
    assert datetime.fromisoformat(row["updated_at"]) > datetime.fromisoformat(old_updated_at)


async def test_extract_and_update_applies_update_ttl_rules(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    old_expiry = (datetime.now(UTC).replace(microsecond=0) + timedelta(days=1)).isoformat()
    _insert_memory_row(
        db_path,
        id="mem-context",
        type="context",
        content="User is working on billing",
        expires_at=old_expiry,
    )
    _insert_memory_row(
        db_path,
        id="mem-preference",
        type="preferences",
        content="User prefers verbose replies",
        expires_at=old_expiry,
    )
    _patch_extraction(
        monkeypatch,
        """
        [
          {
            "action": "update",
            "target_id": "mem-context",
            "type": "context",
            "content": "User is working on payments"
          },
          {
            "action": "update",
            "target_id": "mem-preference",
            "type": "preferences",
            "content": "User prefers concise replies"
          }
        ]
        """,
    )
    before = datetime.now(UTC).replace(microsecond=0) + timedelta(days=30)

    await memory_layer.extract_and_update("alice", [{"role": "user", "content": "facts"}])

    after = datetime.now(UTC).replace(microsecond=0) + timedelta(days=30)
    rows = {row["id"]: row for row in _memory_rows(db_path)}
    context_expires = datetime.fromisoformat(rows["mem-context"]["expires_at"])
    assert before <= context_expires <= after
    assert rows["mem-preference"]["expires_at"] is None


async def test_extract_and_update_upserts_updated_memory_to_vector_store(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    backend = _TrackingBackend()
    embed_text = AsyncMock(return_value=[0.7, 0.8, 0.9])
    vector_upsert = AsyncMock()
    monkeypatch.setattr(store, "_vector_backend", backend, raising=False)
    monkeypatch.setattr(vector_store, "embed_text", embed_text)
    monkeypatch.setattr(vector_store, "upsert", vector_upsert)
    _insert_memory_row(
        db_path,
        id="mem-identity",
        content="User is a backend engineer",
    )
    _patch_extraction(
        monkeypatch,
        """
        [
          {
            "action": "update",
            "target_id": "mem-identity",
            "type": "identity",
            "content": "User is a platform engineer"
          }
        ]
        """,
    )

    await memory_layer.extract_and_update(
        "alice", [{"role": "user", "content": "I am a platform engineer now"}]
    )

    embed_text.assert_awaited_once_with("User is a platform engineer")
    assert backend.upserts == [
        ("mem-identity", [0.7, 0.8, 0.9], vector_store.memory_namespace("alice"))
    ]
    vector_upsert.assert_not_awaited()


async def test_extract_and_update_deletes_existing_memory(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    _insert_memory_row(
        db_path,
        id="mem-context",
        type="context",
        content="User is working on billing",
        expires_at=(datetime.now(UTC).replace(microsecond=0) + timedelta(days=1)).isoformat(),
    )
    _patch_extraction(
        monkeypatch,
        """[{"action": "delete", "target_id": "mem-context"}]""",
    )

    await memory_layer.extract_and_update(
        "alice", [{"role": "user", "content": "Forget that billing context"}]
    )

    assert _memory_rows(db_path) == []


async def test_extract_and_update_deletes_memory_from_vector_store(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    backend = _TrackingBackend()
    vector_delete = AsyncMock()
    monkeypatch.setattr(store, "_vector_backend", backend, raising=False)
    monkeypatch.setattr(vector_store, "delete", vector_delete)
    _insert_memory_row(
        db_path,
        id="mem-context",
        type="context",
        content="User is working on billing",
        expires_at=(datetime.now(UTC).replace(microsecond=0) + timedelta(days=1)).isoformat(),
    )
    _patch_extraction(
        monkeypatch,
        """[{"action": "delete", "target_id": "mem-context"}]""",
    )

    await memory_layer.extract_and_update(
        "alice", [{"role": "user", "content": "Forget that billing context"}]
    )

    assert backend.deletes == [("mem-context", vector_store.memory_namespace("alice"))]
    vector_delete.assert_not_awaited()


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


async def test_extract_and_update_prompt_describes_action_contract(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    create = _patch_extraction(monkeypatch, "[]")

    await memory_layer.extract_and_update("alice", [{"role": "user", "content": "facts"}])

    system_message = create.await_args.kwargs["messages"][0]["content"]
    assert "create" in system_message
    assert "update" in system_message
    assert "delete" in system_message
    assert "ignore" in system_message
    assert "target_id" in system_message
    assert "preferences" in system_message
    assert "one-time" in system_message


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


async def test_extract_and_update_uses_update_for_identity_conflicts_without_duplicate(
    tmp_path, monkeypatch
):
    db_path = _patch_database(tmp_path, monkeypatch)
    _insert_memory_row(
        db_path,
        id="mem-identity",
        content="User is a backend engineer",
    )
    _patch_extraction(
        monkeypatch,
        """
        [
          {
            "action": "update",
            "target_id": "mem-identity",
            "type": "identity",
            "content": "User is a platform engineer"
          }
        ]
        """,
    )

    await memory_layer.extract_and_update(
        "alice", [{"role": "user", "content": "Actually, I am a platform engineer"}]
    )

    rows = _memory_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["id"] == "mem-identity"
    assert rows[0]["content"] == "User is a platform engineer"


async def test_extract_and_update_ignores_one_off_preference_requests(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    _patch_extraction(monkeypatch, """[{"action": "ignore", "reason": "one-time request"}]""")

    await memory_layer.extract_and_update(
        "alice", [{"role": "user", "content": "Use a table for this answer only"}]
    )

    assert _memory_rows(db_path) == []


async def test_search_uses_vector_ids_and_filters_expired_memory(tmp_path, monkeypatch):
    db_path = _patch_database(tmp_path, monkeypatch)
    expired = (datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)).isoformat()
    _insert_memory_row(db_path, id="mem-1", content="User likes Python")
    _insert_memory_row(db_path, id="mem-2", content="User debugs FastAPI")
    _insert_memory_row(
        db_path,
        id="mem-expired",
        type="context",
        content="User is working on an old project",
        expires_at=expired,
    )
    backend = _TrackingBackend(
        results=[
            SearchResult(id="mem-2", score=0.9),
            SearchResult(id="missing", score=0.8),
            SearchResult(id="mem-expired", score=0.7),
            SearchResult(id="mem-1", score=0.6),
        ]
    )
    embed_text = AsyncMock(return_value=[0.2, 0.4, 0.6])
    vector_search = AsyncMock()
    monkeypatch.setattr(store, "_vector_backend", backend, raising=False)
    monkeypatch.setattr(vector_store, "embed_text", embed_text)
    monkeypatch.setattr(vector_store, "search", vector_search)

    results = await memory_layer.search("alice", "python debugging", limit=4)

    embed_text.assert_awaited_once_with("python debugging")
    assert backend.searches == [([0.2, 0.4, 0.6], "mem:alice", 4)]
    vector_search.assert_not_awaited()
    assert [item.id for item in results] == ["mem-2", "mem-1"]
    assert [item.content for item in results] == ["User debugs FastAPI", "User likes Python"]


async def test_extract_and_update_user_scoping_isolates_snapshot(tmp_path, monkeypatch):
    """User-scoping by user_id is preserved: alice's snapshot excludes bob's memories."""
    db_path = _patch_database(tmp_path, monkeypatch)
    _insert_memory_row(db_path, id="alice-id", user_id="alice", content="Alice fact")
    _insert_memory_row(db_path, id="bob-id", user_id="bob", content="Bob fact")
    create = _patch_extraction(monkeypatch, "[]")

    await memory_layer.extract_and_update("alice", [{"role": "user", "content": "facts"}])

    user_message = create.await_args.kwargs["messages"][1]["content"]
    assert "Alice fact" in user_message
    assert "Bob fact" not in user_message


async def test_extract_and_update_does_not_write_legacy_jsonl(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "_vector_backend", _TrackingBackend(), raising=False)
    monkeypatch.setattr(vector_store, "embed_text", AsyncMock(return_value=[0.1, 0.2, 0.3]))
    monkeypatch.setattr(vector_store, "upsert", AsyncMock())
    _patch_extraction(
        monkeypatch,
        """[{"action": "create", "type": "identity", "content": "User is a backend engineer"}]""",
    )

    await memory_layer.extract_and_update(
        "alice", [{"role": "user", "content": "I am a backend engineer"}]
    )

    assert not (tmp_path / "data" / "users" / "alice" / "memories.jsonl").exists()


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
