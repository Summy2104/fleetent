import pytest

from fleetent.db import create_database
from fleetent.vector_store import SearchResult


def _patch_shared_db(monkeypatch, tmp_path):
    from fleetent.memory import store
    from tests.integration.test_migrations import apply_migrations

    db_path = tmp_path / "shared-memory.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(store, "database", lambda: database)
    return database


def test_shared_memory_public_api_is_importable():
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
async def test_create_shared_memory_rejects_invalid_input(monkeypatch, tmp_path, kwargs, message):
    _patch_shared_db(monkeypatch, tmp_path)
    from fleetent.memory import create_shared_memory

    params = {
        "scope_type": "team",
        "scope_id": "eng",
        "type": "context",
        "content": "Team uses GitHub Flow.",
        "created_by": "admin",
    }
    params.update(kwargs)

    with pytest.raises(ValueError, match=message):
        await create_shared_memory(**params)


async def test_create_update_and_archive_sync_vector_store(monkeypatch, tmp_path):
    _patch_shared_db(monkeypatch, tmp_path)
    from fleetent import memory
    from fleetent.memory import shared

    upserts: list[tuple[str, str, str]] = []
    deletes: list[tuple[str, str]] = []

    async def upsert(id: str, text: str, namespace: str) -> None:
        upserts.append((id, text, namespace))

    async def delete(id: str, namespace: str) -> None:
        deletes.append((id, namespace))

    monkeypatch.setattr(shared.vector_store, "upsert", upsert)
    monkeypatch.setattr(shared.vector_store, "delete", delete)

    item = await memory.create_shared_memory(
        scope_type="team",
        scope_id="eng",
        type="procedure",
        content="Deployments use the release checklist.",
        created_by="admin",
    )
    assert upserts == [(item.id, "Deployments use the release checklist.", "shared:team:eng")]

    updated = await memory.update_shared_memory(item.id, content="Use the release checklist.")
    assert updated.content == "Use the release checklist."
    assert upserts[-1] == (item.id, "Use the release checklist.", "shared:team:eng")

    archived = await memory.archive_shared_memory(item.id)
    assert archived.status == "archived"
    assert deletes == [(item.id, "shared:team:eng")]


async def test_search_shared_memory_is_scope_isolated_and_preserves_vector_order(
    monkeypatch, tmp_path
):
    _patch_shared_db(monkeypatch, tmp_path)
    from fleetent import memory
    from fleetent.memory import shared

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

    async def search(query: str, namespace: str, limit: int = 10) -> list[SearchResult]:
        assert namespace == "shared:team:eng"
        return [
            SearchResult(id=second.id, score=0.9),
            SearchResult(id=archived.id, score=0.8),
            SearchResult(id=other_scope.id, score=0.7),
        ]

    monkeypatch.setattr(shared.vector_store, "search", search)

    results = await memory.search_shared_memory("team", "eng", "launch", limit=3)

    assert [item.id for item in results] == [second.id]


async def test_iter_indexable_shared_memories_excludes_archived(monkeypatch, tmp_path):
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


async def test_update_shared_memory_rejects_invalid_status(monkeypatch, tmp_path):
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
