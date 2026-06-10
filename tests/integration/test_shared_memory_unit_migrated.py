"""Unit-migrated integration tests for shared memory CRUD + vector sync.

Updated for shared-memory-lib (3c): patches now inject set_shared_memory_db
instead of store.database, and vector assertions track the injected backend
rather than patching the global vector_store module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.vector_store import SearchResult


def _patch_shared_db(monkeypatch: Any, tmp_path: Path) -> SQLiteDatabase:
    from fleetent.memory import shared
    from fleetent.memory.shared_memory_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("default")
    sm_db = scope.open_shared_memory_db(MIGRATIONS)

    class _NullBackend:
        async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
            pass

        async def search(
            self, vector: list[float], namespace: str, limit: int = 10
        ) -> list[SearchResult]:
            return []

        async def delete(self, id: str, namespace: str) -> None:
            pass

        async def clear_namespace(self, namespace: str) -> None:
            pass

    monkeypatch.setattr(shared, "_shared_memory_db", sm_db)
    monkeypatch.setattr(shared, "_shared_memory_vector_backend", _NullBackend())
    return sm_db


def test_shared_memory_public_api_is_importable() -> None:
    from fleetent.memory import (
        SharedMemoryItem,
        archive_shared_memory,
        create_shared_memory,
        iter_indexable_shared_memories,
        search_shared_memory,
        update_shared_memory,
    )

    assert SharedMemoryItem is not None
    assert callable(create_shared_memory)
    assert callable(update_shared_memory)
    assert callable(archive_shared_memory)
    assert callable(search_shared_memory)
    assert callable(iter_indexable_shared_memories)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"scope_type": "user"}, "scope_type"),
        ({"type": "identity"}, "type"),
        ({"content": "   "}, "content"),
    ],
)
async def test_create_shared_memory_rejects_invalid_input(
    monkeypatch: Any, tmp_path: Path, kwargs: dict[str, Any], message: str
) -> None:
    _patch_shared_db(monkeypatch, tmp_path)
    from fleetent.memory import create_shared_memory

    params: dict[str, Any] = {
        "scope_type": "team",
        "scope_id": "eng",
        "type": "context",
        "content": "Team uses GitHub Flow.",
        "created_by": "admin",
    }
    params.update(kwargs)

    with pytest.raises(ValueError, match=message):
        await create_shared_memory(**params)


async def test_create_update_and_archive_sync_vector_store(
    monkeypatch: Any, tmp_path: Path
) -> None:
    from fleetent.memory import shared
    from fleetent.memory.shared_memory_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("default")
    sm_db = scope.open_shared_memory_db(MIGRATIONS)
    monkeypatch.setattr(shared, "_shared_memory_db", sm_db)

    upserts: list[tuple[str, str]] = []  # (id, namespace)
    deletes: list[tuple[str, str]] = []

    class _TrackingBackend:
        async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
            upserts.append((id, namespace))

        async def search(
            self, vector: list[float], namespace: str, limit: int = 10
        ) -> list[SearchResult]:
            return []

        async def delete(self, id: str, namespace: str) -> None:
            deletes.append((id, namespace))

        async def clear_namespace(self, namespace: str) -> None:
            pass

    monkeypatch.setattr(shared, "_shared_memory_vector_backend", _TrackingBackend())

    from fleetent import memory

    item = await memory.create_shared_memory(
        scope_type="team",
        scope_id="eng",
        type="procedure",
        content="Deployments use the release checklist.",
        created_by="admin",
    )
    assert upserts == [(item.id, "shared:team:eng")]

    updated = await memory.update_shared_memory(item.id, content="Use the release checklist.")
    assert updated.content == "Use the release checklist."
    assert upserts[-1] == (item.id, "shared:team:eng")

    archived = await memory.archive_shared_memory(item.id)
    assert archived.status == "archived"
    assert deletes == [(item.id, "shared:team:eng")]


async def test_search_shared_memory_is_scope_isolated_and_preserves_vector_order(
    monkeypatch: Any, tmp_path: Path
) -> None:
    from fleetent.memory import shared
    from fleetent.memory.shared_memory_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("default")
    sm_db = scope.open_shared_memory_db(MIGRATIONS)
    monkeypatch.setattr(shared, "_shared_memory_db", sm_db)

    from fleetent import memory

    # Pre-create items with a null backend (no vector calls needed for setup)
    class _NullBackend:
        async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
            pass

        async def search(
            self, vector: list[float], namespace: str, limit: int = 10
        ) -> list[SearchResult]:
            return []

        async def delete(self, id: str, namespace: str) -> None:
            pass

        async def clear_namespace(self, namespace: str) -> None:
            pass

    monkeypatch.setattr(shared, "_shared_memory_vector_backend", _NullBackend())

    first = await memory.create_shared_memory(
        scope_type="team",
        scope_id="eng",
        type="context",
        content="The API team owns billing webhooks.",
        created_by="admin",
    )
    second = await memory.create_shared_memory(
        scope_type="team",
        scope_id="eng",
        type="preference",
        content="Prefer concise launch summaries.",
        created_by="admin",
    )
    other_scope = await memory.create_shared_memory(
        scope_type="team",
        scope_id="sales",
        type="context",
        content="The sales team owns renewal notes.",
        created_by="admin",
    )
    archived = await memory.archive_shared_memory(first.id)

    # Now swap to a search-returning backend
    class _SearchBackend:
        async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
            pass

        async def search(
            self, vector: list[float], namespace: str, limit: int = 10
        ) -> list[SearchResult]:
            assert namespace == "shared:team:eng"
            return [
                SearchResult(id=second.id, score=0.9),
                SearchResult(id=archived.id, score=0.8),
                SearchResult(id=other_scope.id, score=0.7),
            ]

        async def delete(self, id: str, namespace: str) -> None:
            pass

        async def clear_namespace(self, namespace: str) -> None:
            pass

    monkeypatch.setattr(shared, "_shared_memory_vector_backend", _SearchBackend())

    results = await memory.search_shared_memory("team", "eng", "launch", limit=3)

    assert [item.id for item in results] == [second.id]


async def test_iter_indexable_shared_memories_excludes_archived(
    monkeypatch: Any, tmp_path: Path
) -> None:
    _patch_shared_db(monkeypatch, tmp_path)
    from fleetent import memory

    item = await memory.create_shared_memory(
        scope_type="tenant",
        scope_id="acme",
        type="preference",
        content="Use customer-facing names in demos.",
        created_by="admin",
    )
    archived = await memory.create_shared_memory(
        scope_type="tenant",
        scope_id="acme",
        type="context",
        content="Archived item.",
        created_by="admin",
    )
    await memory.archive_shared_memory(archived.id)

    rows = list(memory.iter_indexable_shared_memories("tenant", "acme"))

    assert [(row.id, row.content, row.namespace) for row in rows] == [
        (item.id, "Use customer-facing names in demos.", "shared:tenant:acme")
    ]
    assert rows[0].metadata == {"type": "preference", "scope_type": "tenant"}


async def test_update_shared_memory_rejects_invalid_status(
    monkeypatch: Any, tmp_path: Path
) -> None:
    _patch_shared_db(monkeypatch, tmp_path)
    from fleetent import memory

    item = await memory.create_shared_memory(
        scope_type="team",
        scope_id="eng",
        type="context",
        content="Team context.",
        created_by="admin",
    )

    with pytest.raises(ValueError, match="status"):
        await memory.update_shared_memory(item.id, status="deleted")
