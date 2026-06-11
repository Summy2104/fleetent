"""Public User Memory operations."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

from fleetent import vector_store
from fleetent.memory import store
from fleetent.memory.extraction import expires_at
from fleetent.memory.models import MemoryItem


async def update_user_memory_content(user_id: str, memory_id: str, content: str) -> None:
    """Update one User Memory item through the public memory-layer boundary."""
    item = store.get_user_memory(user_id, memory_id)
    if item is None:
        raise ValueError("memory item does not exist for user")
    now = datetime.now(UTC).replace(microsecond=0)
    updated = MemoryItem(
        id=item.id,
        user_id=item.user_id,
        type=item.type,
        content=content.strip(),
        created_at=item.created_at,
        updated_at=now,
        expires_at=expires_at(item.type, now),
    )
    store.update_memory(updated)
    vector = await vector_store.embed_text(updated.content)
    await store.vector_backend().upsert(updated.id, vector, vector_store.memory_namespace(user_id))


async def mark_user_memory_stale(user_id: str, memory_id: str) -> None:
    """Mark one User Memory item stale without changing ownership or scope."""
    item = store.get_user_memory(user_id, memory_id)
    if item is None:
        raise ValueError("memory item does not exist for user")
    now = datetime.now(UTC).replace(microsecond=0)
    updated = MemoryItem(
        id=item.id,
        user_id=item.user_id,
        type=item.type,
        content=item.content,
        created_at=item.created_at,
        updated_at=now,
        expires_at=now,
    )
    store.update_memory(updated)
    await store.vector_backend().delete(updated.id, vector_store.memory_namespace(user_id))


async def delete_user_memory(user_id: str, memory_id: str) -> None:
    """Delete one User Memory item through the public memory-layer boundary."""
    store.delete_memory(user_id, memory_id)
    await store.vector_backend().delete(memory_id, vector_store.memory_namespace(user_id))


async def merge_user_memories(
    user_id: str,
    target_memory_ids: list[str],
    merged_content: str,
) -> None:
    """Merge User Memory items by updating the first target and deleting the rest."""
    if not target_memory_ids:
        raise ValueError("target_memory_ids must not be empty")
    canonical_id = target_memory_ids[0]
    await update_user_memory_content(user_id, canonical_id, merged_content)
    for duplicate_id in target_memory_ids[1:]:
        await delete_user_memory(user_id, duplicate_id)


def iter_indexable_memories(user_id: str) -> Iterator[vector_store.IndexableItem]:
    """Yield current memory records that should exist in vector_store."""
    namespace = vector_store.memory_namespace(user_id)
    for row in store.indexable_memory_rows(user_id):
        yield vector_store.IndexableItem(
            id=str(row["id"]),
            content=str(row["content"]),
            namespace=namespace,
            metadata={"type": str(row["type"])},
        )
