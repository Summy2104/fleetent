"""Agent Memory public operations.

Connection source: agent_state.db via ``agent_scope.open_state_db(AGENT_STATE_MIGRATIONS)``
in agent_app._init_agent_db_schema.  Call ``set_agent_memory_db(state_db, backend)``
once at agent boot before any reads or writes.

Vector operations use the injected per-agent vector backend
(agentmem: family, per-agent) rather than the global vector_store backend.
Embedding still uses the global provider via ``vector_store.embed_text``.
Isolation is provided by the per-agent physical DB — no scope columns needed.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import cast

from fleetent import vector_store
from fleetent.db import SQLiteDatabase
from fleetent.memory._datetime_utils import format_datetime, parse_datetime
from fleetent.memory.models import (
    AgentMemoryItem,
    AgentMemorySource,
    AgentMemoryStatus,
    AgentMemoryType,
)
from fleetent.memory.proposal_store import (
    get_memory_maintenance_proposal,
    mark_agent_memory_proposal_applied,
)
from fleetent.vector_store.backend import VectorBackend

_TYPES = {"context", "preference", "procedure"}
_STATUSES = {"active", "stale", "archived"}
_SOURCES = {"manual", "reflection_proposal"}

_agent_memory_db: SQLiteDatabase | None = None
_vector_backend: VectorBackend | None = None

_NAMESPACE = vector_store.agent_memory_namespace()


def set_agent_memory_db(db: SQLiteDatabase, vector_backend: VectorBackend) -> None:
    """Inject the per-agent memory DB and vector backend.

    Called once at agent boot after ``agent_scope.open_state_db(AGENT_STATE_MIGRATIONS)``.
    """
    global _agent_memory_db, _vector_backend
    _agent_memory_db = db
    _vector_backend = vector_backend


def _agent_memory_database() -> SQLiteDatabase:
    if _agent_memory_db is None:
        raise RuntimeError(
            "memory/agent_memory: agent_memory_db not initialized"
            " — call set_agent_memory_db(db, backend) at boot"
        )
    return _agent_memory_db


def _agent_memory_backend() -> VectorBackend:
    if _vector_backend is None:
        raise RuntimeError(
            "memory/agent_memory: vector backend not initialized"
            " — call set_agent_memory_db(db, backend) at boot"
        )
    return _vector_backend


async def create_agent_memory(
    *,
    type: str,
    content: str,
    created_by: str,
    source: str = "manual",
    source_ref: str | None = None,
) -> AgentMemoryItem:
    """Create an Agent Memory item and index active content."""
    item = _new_item(
        type=type,
        content=content,
        created_by=created_by,
        source=source,
        source_ref=source_ref,
    )
    _insert(item)
    await _sync_vector(item)
    return item


async def update_agent_memory(
    item_id: str,
    *,
    content: str | None = None,
    type: str | None = None,
    status: str | None = None,
) -> AgentMemoryItem:
    """Update an Agent Memory item and synchronize its vector state."""
    item = get_agent_memory(item_id)
    now = datetime.now(UTC).replace(microsecond=0)
    updated = AgentMemoryItem(
        id=item.id,
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


async def archive_agent_memory(item_id: str) -> AgentMemoryItem:
    """Archive an Agent Memory item and remove it from vector search."""
    return await update_agent_memory(item_id, status="archived")


async def search_agent_memory(
    query: str,
    limit: int = 10,
) -> list[AgentMemoryItem]:
    """Return active or stale Agent Memory items in vector relevance order."""
    query_vector = await vector_store.embed_text(query)
    vector_results = await _agent_memory_backend().search(query_vector, _NAMESPACE, limit)
    ids = [result.id for result in vector_results]
    by_id = _items_by_ids(ids)
    return [
        item
        for item_id in ids
        if (item := by_id.get(item_id)) is not None and item.status in {"active", "stale"}
    ]


def iter_indexable_agent_memories() -> Iterator[vector_store.IndexableItem]:
    """Yield Agent Memory records that should exist in vector_store."""
    for item in list_agent_memory(include_archived=False):
        yield vector_store.IndexableItem(
            id=item.id,
            content=item.content,
            namespace=_NAMESPACE,
            metadata={"type": item.type},
        )


def get_agent_memory(item_id: str) -> AgentMemoryItem:
    """Load one Agent Memory item by id."""
    row = (
        _agent_memory_database()
        .execute(
            """
            SELECT *
            FROM agent_memory_items
            WHERE id = :id
            """,
            {"id": item_id},
        )
        .fetchone()
    )
    if row is None:
        raise ValueError("agent memory item does not exist")
    return _row_to_item(row)


def list_agent_memory(
    *,
    include_archived: bool = False,
) -> list[AgentMemoryItem]:
    """List Agent Memory items for this agent."""
    clauses = []
    params: dict[str, object] = {}
    if not include_archived:
        clauses.append("status != :archived")
        params["archived"] = "archived"
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = (
        _agent_memory_database()
        .execute(
            f"""
            SELECT *
            FROM agent_memory_items
            {where}
            ORDER BY updated_at DESC, id ASC
            """,
            params,
        )
        .fetchall()
    )
    return [_row_to_item(row) for row in rows]


async def apply_agent_memory_proposal(proposal_id: str, *, actor_id: str) -> AgentMemoryItem:
    """Apply an approved reflection maintenance proposal as Agent Memory."""
    proposal = get_memory_maintenance_proposal(proposal_id)
    if proposal.action != "suggest_agent_memory_or_kb":
        raise ValueError("proposal is not an agent memory suggestion")
    if proposal.metadata_patch.get("target") != "agent_memory":
        raise ValueError("proposal target is not agent_memory")

    memory_type = proposal.metadata_patch.get("type", "")
    item = await create_agent_memory(
        type=memory_type,
        content=_require_proposed_content(proposal.proposed_content),
        created_by=actor_id,
        source="reflection_proposal",
        source_ref=proposal.id,
    )
    mark_agent_memory_proposal_applied(proposal.id)
    return item


def _new_item(
    *,
    type: str,
    content: str,
    created_by: str,
    source: str,
    source_ref: str | None,
) -> AgentMemoryItem:
    now = datetime.now(UTC).replace(microsecond=0)
    return AgentMemoryItem(
        id=str(uuid.uuid4()),
        type=_validate_type(type),
        content=_validate_content(content),
        status="active",
        source=_validate_source(source),
        source_ref=source_ref,
        created_by=_validate_non_empty(created_by, "created_by"),
        created_at=now,
        updated_at=now,
    )


def _insert(item: AgentMemoryItem) -> None:
    _agent_memory_database().execute(
        """
        INSERT INTO agent_memory_items (
            id, type, content, status, source, source_ref,
            created_by, created_at, updated_at
        )
        VALUES (
            :id, :type, :content, :status, :source, :source_ref,
            :created_by, :created_at, :updated_at
        )
        """,
        _params(item),
    )


def _update(item: AgentMemoryItem) -> None:
    _agent_memory_database().execute(
        """
        UPDATE agent_memory_items
        SET type = :type,
            content = :content,
            status = :status,
            updated_at = :updated_at
        WHERE id = :id
        """,
        _params(item),
    )


def _items_by_ids(ids: list[str]) -> dict[str, AgentMemoryItem]:
    if not ids:
        return {}
    placeholders = ", ".join(f":id_{index}" for index in range(len(ids)))
    params: dict[str, object] = {f"id_{index}": item_id for index, item_id in enumerate(ids)}
    rows = (
        _agent_memory_database()
        .execute(
            f"""
            SELECT *
            FROM agent_memory_items
            WHERE id IN ({placeholders})
            """,
            params,
        )
        .fetchall()
    )
    return {str(row["id"]): _row_to_item(row) for row in rows}


async def _sync_vector(item: AgentMemoryItem) -> None:
    backend = _agent_memory_backend()
    if item.status in {"active", "stale"}:
        vector = await vector_store.embed_text(item.content)
        await backend.upsert(item.id, vector, _NAMESPACE)
        return
    await backend.delete(item.id, _NAMESPACE)


def _row_to_item(row: dict[str, object]) -> AgentMemoryItem:
    return AgentMemoryItem(
        id=str(row["id"]),
        type=cast(AgentMemoryType, row["type"]),
        content=str(row["content"]),
        status=cast(AgentMemoryStatus, row["status"]),
        source=cast(AgentMemorySource, row["source"]),
        source_ref=str(row["source_ref"]) if row["source_ref"] is not None else None,
        created_by=str(row["created_by"]),
        created_at=parse_datetime(row["created_at"]),
        updated_at=parse_datetime(row["updated_at"]),
    )


def _params(item: AgentMemoryItem) -> dict[str, object]:
    return {
        "id": item.id,
        "type": item.type,
        "content": item.content,
        "status": item.status,
        "source": item.source,
        "source_ref": item.source_ref,
        "created_by": item.created_by,
        "created_at": format_datetime(item.created_at),
        "updated_at": format_datetime(item.updated_at),
    }


def _validate_type(value: str) -> AgentMemoryType:
    if value not in _TYPES:
        raise ValueError("type must be context, preference, or procedure")
    return cast(AgentMemoryType, value)


def _validate_status(value: str) -> AgentMemoryStatus:
    if value not in _STATUSES:
        raise ValueError("status must be active, stale, or archived")
    return cast(AgentMemoryStatus, value)


def _validate_source(value: str) -> AgentMemorySource:
    if value not in _SOURCES:
        raise ValueError("source must be manual or reflection_proposal")
    return cast(AgentMemorySource, value)


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
