"""Shared Memory public operations."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import cast

from fleetent import vector_store
from fleetent.memory import store
from fleetent.memory.models import (
    SharedMemoryItem,
    SharedMemoryScopeType,
    SharedMemorySource,
    SharedMemoryStatus,
    SharedMemoryType,
)
from fleetent.memory.proposal_store import (
    get_memory_maintenance_proposal,
    mark_shared_memory_proposal_applied,
)

_SCOPE_TYPES = {"team", "tenant"}
_TYPES = {"context", "preference", "procedure"}
_STATUSES = {"active", "stale", "archived"}
_SOURCES = {"manual", "reflection_proposal"}


async def create_shared_memory(
    *,
    scope_type: str,
    scope_id: str,
    type: str,
    content: str,
    created_by: str,
    source: str = "manual",
    source_ref: str | None = None,
) -> SharedMemoryItem:
    """Create a Shared Memory item and index active content."""
    item = _new_item(
        scope_type=scope_type,
        scope_id=scope_id,
        type=type,
        content=content,
        created_by=created_by,
        source=source,
        source_ref=source_ref,
    )
    _insert(item)
    await _sync_vector(item)
    return item


async def update_shared_memory(
    item_id: str,
    *,
    content: str | None = None,
    type: str | None = None,
    status: str | None = None,
) -> SharedMemoryItem:
    """Update a Shared Memory item and synchronize its vector state."""
    item = get_shared_memory(item_id)
    now = datetime.now(UTC).replace(microsecond=0)
    updated = SharedMemoryItem(
        id=item.id,
        scope_type=item.scope_type,
        scope_id=item.scope_id,
        type=_validate_type(type) if type is not None else item.type,
        content=_validate_content(content) if content is not None else item.content,
        status=_validate_status(status) if status is not None else item.status,
        source=item.source,
        source_ref=item.source_ref,
        created_by=item.created_by,
        created_at=item.created_at,
        updated_at=now,
    )
    _update(updated)
    await _sync_vector(updated)
    return updated


async def archive_shared_memory(item_id: str) -> SharedMemoryItem:
    """Archive a Shared Memory item and remove it from vector search."""
    return await update_shared_memory(item_id, status="archived")


async def search_shared_memory(
    scope_type: str,
    scope_id: str,
    query: str,
    limit: int = 10,
) -> list[SharedMemoryItem]:
    """Return active or stale Shared Memory items in vector relevance order."""
    scope = _validate_scope_type(scope_type)
    scope_identifier = _validate_non_empty(scope_id, "scope_id")
    namespace = vector_store.shared_namespace(scope, scope_identifier)
    vector_results = await vector_store.search(query, namespace, limit)
    ids = [result.id for result in vector_results]
    by_id = _items_by_ids(scope, scope_identifier, ids)
    return [
        item
        for item_id in ids
        if (item := by_id.get(item_id)) is not None and item.status in {"active", "stale"}
    ]


def iter_indexable_shared_memories(
    scope_type: str,
    scope_id: str,
) -> Iterator[vector_store.IndexableItem]:
    """Yield Shared Memory records that should exist in vector_store."""
    scope = _validate_scope_type(scope_type)
    scope_identifier = _validate_non_empty(scope_id, "scope_id")
    namespace = vector_store.shared_namespace(scope, scope_identifier)
    for item in list_shared_memory(scope, scope_identifier, include_archived=False):
        yield vector_store.IndexableItem(
            id=item.id,
            content=item.content,
            namespace=namespace,
            metadata={"type": item.type, "scope_type": item.scope_type},
        )


def get_shared_memory(item_id: str) -> SharedMemoryItem:
    """Load one Shared Memory item by id."""
    row = (
        store.database()
        .execute(
            """
            SELECT *
            FROM shared_memory_items
            WHERE id = :id
            """,
            {"id": item_id},
        )
        .fetchone()
    )
    if row is None:
        raise ValueError("shared memory item does not exist")
    return _row_to_item(row)


def list_shared_memory(
    scope_type: str,
    scope_id: str,
    *,
    include_archived: bool = False,
) -> list[SharedMemoryItem]:
    """List Shared Memory items for one scope."""
    scope = _validate_scope_type(scope_type)
    scope_identifier = _validate_non_empty(scope_id, "scope_id")
    clauses = ["scope_type = :scope_type", "scope_id = :scope_id"]
    params: dict[str, object] = {"scope_type": scope, "scope_id": scope_identifier}
    if not include_archived:
        clauses.append("status != :archived")
        params["archived"] = "archived"
    rows = (
        store.database()
        .execute(
            f"""
            SELECT *
            FROM shared_memory_items
            WHERE {" AND ".join(clauses)}
            ORDER BY updated_at DESC, id ASC
            """,
            params,
        )
        .fetchall()
    )
    return [_row_to_item(row) for row in rows]


async def apply_shared_memory_proposal(proposal_id: str, *, actor_id: str) -> SharedMemoryItem:
    """Apply an approved reflection maintenance proposal as Shared Memory."""
    proposal = get_memory_maintenance_proposal(proposal_id)
    if proposal.action != "suggest_shared_memory_or_kb":
        raise ValueError("proposal is not a shared memory suggestion")
    if proposal.metadata_patch.get("target") != "shared_memory":
        raise ValueError("proposal target is not shared_memory")

    scope_type = proposal.metadata_patch.get("scope_type", "")
    scope_id = proposal.metadata_patch.get("scope_id", "")
    memory_type = proposal.metadata_patch.get("type", "")
    item = await create_shared_memory(
        scope_type=scope_type,
        scope_id=scope_id,
        type=memory_type,
        content=_require_proposed_content(proposal.proposed_content),
        created_by=actor_id,
        source="reflection_proposal",
        source_ref=proposal.id,
    )
    mark_shared_memory_proposal_applied(proposal.id)
    return item


def _new_item(
    *,
    scope_type: str,
    scope_id: str,
    type: str,
    content: str,
    created_by: str,
    source: str,
    source_ref: str | None,
) -> SharedMemoryItem:
    now = datetime.now(UTC).replace(microsecond=0)
    return SharedMemoryItem(
        id=str(uuid.uuid4()),
        scope_type=_validate_scope_type(scope_type),
        scope_id=_validate_non_empty(scope_id, "scope_id"),
        type=_validate_type(type),
        content=_validate_content(content),
        status="active",
        source=_validate_source(source),
        source_ref=source_ref,
        created_by=_validate_non_empty(created_by, "created_by"),
        created_at=now,
        updated_at=now,
    )


def _insert(item: SharedMemoryItem) -> None:
    store.database().execute(
        """
        INSERT INTO shared_memory_items (
            id, scope_type, scope_id, type, content, status, source, source_ref,
            created_by, created_at, updated_at
        )
        VALUES (
            :id, :scope_type, :scope_id, :type, :content, :status, :source, :source_ref,
            :created_by, :created_at, :updated_at
        )
        """,
        _params(item),
    )


def _update(item: SharedMemoryItem) -> None:
    store.database().execute(
        """
        UPDATE shared_memory_items
        SET type = :type,
            content = :content,
            status = :status,
            updated_at = :updated_at
        WHERE id = :id
        """,
        _params(item),
    )


def _items_by_ids(
    scope_type: SharedMemoryScopeType,
    scope_id: str,
    ids: list[str],
) -> dict[str, SharedMemoryItem]:
    if not ids:
        return {}
    placeholders = ", ".join(f":id_{index}" for index in range(len(ids)))
    params: dict[str, object] = {
        "scope_type": scope_type,
        "scope_id": scope_id,
        **{f"id_{index}": item_id for index, item_id in enumerate(ids)},
    }
    rows = (
        store.database()
        .execute(
            f"""
            SELECT *
            FROM shared_memory_items
            WHERE scope_type = :scope_type
              AND scope_id = :scope_id
              AND id IN ({placeholders})
            """,
            params,
        )
        .fetchall()
    )
    return {str(row["id"]): _row_to_item(row) for row in rows}


async def _sync_vector(item: SharedMemoryItem) -> None:
    namespace = vector_store.shared_namespace(item.scope_type, item.scope_id)
    if item.status in {"active", "stale"}:
        await vector_store.upsert(item.id, item.content, namespace)
        return
    await vector_store.delete(item.id, namespace)


def _row_to_item(row: dict[str, object]) -> SharedMemoryItem:
    return SharedMemoryItem(
        id=str(row["id"]),
        scope_type=cast(SharedMemoryScopeType, row["scope_type"]),
        scope_id=str(row["scope_id"]),
        type=cast(SharedMemoryType, row["type"]),
        content=str(row["content"]),
        status=cast(SharedMemoryStatus, row["status"]),
        source=cast(SharedMemorySource, row["source"]),
        source_ref=str(row["source_ref"]) if row["source_ref"] is not None else None,
        created_by=str(row["created_by"]),
        created_at=store.parse_datetime(row["created_at"]),
        updated_at=store.parse_datetime(row["updated_at"]),
    )


def _params(item: SharedMemoryItem) -> dict[str, object]:
    return {
        "id": item.id,
        "scope_type": item.scope_type,
        "scope_id": item.scope_id,
        "type": item.type,
        "content": item.content,
        "status": item.status,
        "source": item.source,
        "source_ref": item.source_ref,
        "created_by": item.created_by,
        "created_at": store.format_datetime(item.created_at),
        "updated_at": store.format_datetime(item.updated_at),
    }


def _validate_scope_type(value: str) -> SharedMemoryScopeType:
    if value not in _SCOPE_TYPES:
        raise ValueError("scope_type must be team or tenant")
    return cast(SharedMemoryScopeType, value)


def _validate_type(value: str) -> SharedMemoryType:
    if value not in _TYPES:
        raise ValueError("type must be context, preference, or procedure")
    return cast(SharedMemoryType, value)


def _validate_status(value: str) -> SharedMemoryStatus:
    if value not in _STATUSES:
        raise ValueError("status must be active, stale, or archived")
    return cast(SharedMemoryStatus, value)


def _validate_source(value: str) -> SharedMemorySource:
    if value not in _SOURCES:
        raise ValueError("source must be manual or reflection_proposal")
    return cast(SharedMemorySource, value)


def _validate_content(value: str) -> str:
    return _validate_non_empty(value, "content")


def _validate_non_empty(value: str, name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name} must not be empty")
    return stripped


def _require_proposed_content(value: str | None) -> str:
    if value is None or not value.strip():
        raise ValueError("proposed_content is required")
    return value.strip()
