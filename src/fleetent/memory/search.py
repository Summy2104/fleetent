"""Semantic search for User Memory."""

from __future__ import annotations

from datetime import UTC, datetime

from fleetent import vector_store
from fleetent.memory import store
from fleetent.memory.models import MemoryItem


async def search(user_id: str, query: str, limit: int = 10) -> list[MemoryItem]:
    """Return semantically relevant, non-expired memory items."""
    vector_ns = vector_store.memory_namespace(user_id)
    query_vector = await vector_store.embed_text(query)
    vector_results = await store.vector_backend().search(query_vector, vector_ns, limit)
    ids = [result.id for result in vector_results]
    if not ids:
        return []

    by_id = store.memory_items_by_ids(user_id, ids)
    now = datetime.now(UTC).replace(microsecond=0)
    return [
        item
        for id in ids
        if (item := by_id.get(id)) is not None
        and (item.expires_at is None or item.expires_at >= now)
    ]
