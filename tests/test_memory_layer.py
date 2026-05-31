import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fleetent import memory_layer
from fleetent.intelligence import vector_store
from tests.test_migrations import apply_migrations


def test_memory_layer_public_api_exports_semantic_store_contract():
    assert memory_layer.MemoryItem
    assert callable(memory_layer.extract_and_update)
    assert callable(memory_layer.search)
    assert not hasattr(memory_layer, "load_memories")


def _patch_database(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def _patch_extraction(monkeypatch, content: str) -> AsyncMock:
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace()))
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )
    )
    client.chat.completions.create = create
    cfg = SimpleNamespace(model="test-memory-model", max_tokens=512)
    monkeypatch.setattr(memory_layer, "get_async_client_and_config", lambda _: (client, cfg))
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
    expires_at: str | None = None,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memory_items (
                id, user_id, type, content, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (id, user_id, type, content, now, now, expires_at),
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
    upsert = AsyncMock()
    monkeypatch.setattr(vector_store, "upsert", upsert)
    _patch_extraction(
        monkeypatch,
        """[{"action": "create", "type": "identity", "content": "User is a backend engineer"}]""",
    )

    await memory_layer.extract_and_update(
        "alice", [{"role": "user", "content": "I am a backend engineer"}]
    )

    [row] = _memory_rows(db_path)
    upsert.assert_awaited_once_with(
        row["id"], "User is a backend engineer", vector_store.memory_namespace("alice")
    )


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
    vector_search = AsyncMock(
        return_value=[
            vector_store.SearchResult(id="mem-2", score=0.9),
            vector_store.SearchResult(id="missing", score=0.8),
            vector_store.SearchResult(id="mem-expired", score=0.7),
            vector_store.SearchResult(id="mem-1", score=0.6),
        ]
    )
    monkeypatch.setattr(vector_store, "search", vector_search)

    results = await memory_layer.search("alice", "python debugging", limit=4)

    vector_search.assert_awaited_once_with("python debugging", "mem:alice", 4)
    assert [item.id for item in results] == ["mem-2", "mem-1"]
    assert [item.content for item in results] == ["User debugs FastAPI", "User likes Python"]


async def test_extract_and_update_does_not_write_legacy_jsonl(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(vector_store, "upsert", AsyncMock())
    _patch_extraction(
        monkeypatch,
        """[{"action": "create", "type": "identity", "content": "User is a backend engineer"}]""",
    )

    await memory_layer.extract_and_update(
        "alice", [{"role": "user", "content": "I am a backend engineer"}]
    )

    assert not (tmp_path / "data" / "users" / "alice" / "memories.jsonl").exists()
