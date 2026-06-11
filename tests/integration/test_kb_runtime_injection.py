from __future__ import annotations

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.schema_migrations import migrate
from fleetent.vector_store.backend import SearchResult


def test_runtime_database_requires_explicit_injection(tmp_path) -> None:
    from fleetent.knowledge_base import runtime

    db_path = tmp_path / "kb.db"
    migrate(SQLiteDatabase(path=db_path), KB_MIGRATIONS)
    database = SQLiteDatabase(path=db_path)

    runtime.set_database(None)

    with pytest.raises(RuntimeError, match="set_database"):
        runtime._database()

    runtime.set_database(database)

    assert runtime._database() is database

    runtime.set_database(None)


async def test_runtime_search_uses_injected_vector_backend(monkeypatch, tmp_path) -> None:
    from fleetent.knowledge_base import runtime

    db_path = tmp_path / "kb.db"
    migrate(SQLiteDatabase(path=db_path), KB_MIGRATIONS)
    database = SQLiteDatabase(path=db_path)

    class FakeVectorBackend:
        def __init__(self) -> None:
            self.calls: list[tuple[list[float], str, int]] = []

        async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
            return None

        async def search(
            self, vector: list[float], namespace: str, limit: int = 10
        ) -> list[SearchResult]:
            self.calls.append((vector, namespace, limit))
            return [SearchResult(id=f"{document.id}:chunk:0", score=0.75)]

        async def delete(self, id: str, namespace: str) -> None:
            return None

        async def clear_namespace(self, namespace: str) -> None:
            return None

    runtime.set_database(database)
    fake_backend = FakeVectorBackend()
    runtime.set_vector_backend(fake_backend)
    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    monkeypatch.setattr(runtime.vector_store, "embed_text", _embed_query)
    monkeypatch.setattr(runtime.vector_store, "search", _unexpected_global_search)

    document = await runtime.ingest_text(
        filename="guide.txt",
        content="tenant handbook",
        tenant_id="tenant-a",
        kb_id="global",
    )

    results = await runtime.search("handbook", tenant_id="tenant-a", kb_ids=["global"], limit=3)

    assert fake_backend.calls == [([1.0, 0.0], "kb:tenant-a:global", 3)]
    assert [(chunk.id, chunk.filename, chunk.content, chunk.score) for chunk in results] == [
        (f"{document.id}:chunk:0", "guide.txt", "tenant handbook", 0.75)
    ]

    runtime.set_vector_backend(None)
    runtime.set_database(None)


async def _noop_upsert(chunk_id: str, content: str, namespace: str) -> None:
    return None


async def _embed_query(text: str) -> list[float]:
    assert text in {"handbook", "tenant handbook"}
    return [1.0, 0.0]


async def _unexpected_global_search(query: str, namespace: str, limit: int = 10):
    raise AssertionError("global vector_store.search bypass must not be used")
