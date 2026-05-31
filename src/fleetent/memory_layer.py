"""Structured per-user semantic memory store."""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.intelligence import vector_store
from fleetent.model_router import get_async_client_and_config

MemoryType = Literal["identity", "preferences", "context"]

_EXTRACT_SYSTEM = (
    "Extract user semantic memories from the conversation. Return a JSON array of actions. "
    "Use action=create with type identity, preferences, or context and non-empty content. "
    "Use action=update with target_id, matching type, and non-empty content when the "
    "conversation corrects an existing identity, preferences, or context memory. "
    "Use action=delete with target_id when the user asks to forget an existing memory. "
    "Use action=ignore for facts that should not be remembered, including uncertain facts "
    "and one-time preferences or formatting requests."
)
_VALID_TYPES = {"identity", "preferences", "context"}
_CONTEXT_TTL = timedelta(days=30)
_SNAPSHOT_LIMITS: dict[MemoryType, int] = {
    "identity": 20,
    "preferences": 30,
    "context": 20,
}


@dataclass(frozen=True)
class MemoryItem:
    """A structured semantic memory item."""

    id: str
    user_id: str
    type: MemoryType
    content: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None


async def extract_and_update(user_id: str, conversation: list[dict[str, Any]]) -> None:
    """Extract structured memories from conversation and update the memory store."""
    snapshot = _memory_snapshot(user_id)
    client, cfg = get_async_client_and_config("memory_extraction")
    response = await client.chat.completions.create(
        model=cfg.model,
        messages=[
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {"role": "user", "content": _extraction_user_message(conversation, snapshot)},
        ],
        max_tokens=cfg.max_tokens,
    )
    raw = _strip_markdown_fence(response.choices[0].message.content or "[]")
    try:
        actions = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(actions, list):
        return

    now = datetime.now(UTC).replace(microsecond=0)
    snapshot_by_id = {item.id: item for items in snapshot.values() for item in items}
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_name = action.get("action")
        if action_name == "delete":
            target_id = action.get("target_id")
            target = snapshot_by_id.get(target_id) if isinstance(target_id, str) else None
            if target is None:
                continue
            _delete_memory(user_id, target.id)
            await vector_store.delete(target.id, vector_store.memory_namespace(user_id))
            continue
        content = action.get("content")
        raw_type = action.get("type")
        if not isinstance(content, str) or not content.strip() or raw_type not in _VALID_TYPES:
            continue
        memory_type = cast(MemoryType, raw_type)
        if action_name == "update":
            target_id = action.get("target_id")
            target = snapshot_by_id.get(target_id) if isinstance(target_id, str) else None
            if target is None or target.type != memory_type:
                continue
            updated = MemoryItem(
                id=target.id,
                user_id=user_id,
                type=target.type,
                content=content.strip(),
                created_at=target.created_at,
                updated_at=now,
                expires_at=_expires_at(memory_type, now),
            )
            _update_memory(updated)
            await vector_store.upsert(
                updated.id, updated.content, vector_store.memory_namespace(user_id)
            )
            continue
        if action_name != "create":
            continue
        item = MemoryItem(
            id=str(uuid.uuid4()),
            user_id=user_id,
            type=memory_type,
            content=content.strip(),
            created_at=now,
            updated_at=now,
            expires_at=_expires_at(memory_type, now),
        )
        _insert_memory(item)
        await vector_store.upsert(item.id, item.content, vector_store.memory_namespace(user_id))


async def search(user_id: str, query: str, limit: int = 10) -> list[MemoryItem]:
    """Return semantically relevant, non-expired memory items."""
    vector_results = await vector_store.search(query, vector_store.memory_namespace(user_id), limit)
    ids = [result.id for result in vector_results]
    if not ids:
        return []

    placeholders = ", ".join(f":id_{index}" for index in range(len(ids)))
    params = {f"id_{index}": id for index, id in enumerate(ids)}
    params["user_id"] = user_id
    rows = (
        _database()
        .execute(
            f"""
        SELECT id, user_id, type, content, created_at, updated_at, expires_at
        FROM memory_items
        WHERE user_id = :user_id AND id IN ({placeholders})
        """,
            params,
        )
        .fetchall()
    )
    by_id = {row["id"]: _row_to_memory_item(row) for row in rows}
    now = datetime.now(UTC).replace(microsecond=0)
    return [
        item
        for id in ids
        if (item := by_id.get(id)) is not None
        and (item.expires_at is None or item.expires_at >= now)
    ]


def _insert_memory(item: MemoryItem) -> None:
    _database().execute(
        """
        INSERT INTO memory_items (
            id, user_id, type, content, created_at, updated_at, expires_at
        )
        VALUES (
            :id, :user_id, :type, :content, :created_at, :updated_at, :expires_at
        )
        """,
        {
            "id": item.id,
            "user_id": item.user_id,
            "type": item.type,
            "content": item.content,
            "created_at": _format_datetime(item.created_at),
            "updated_at": _format_datetime(item.updated_at),
            "expires_at": _format_datetime(item.expires_at),
        },
    )


def _update_memory(item: MemoryItem) -> None:
    _database().execute(
        """
        UPDATE memory_items
        SET content = :content,
            updated_at = :updated_at,
            expires_at = :expires_at
        WHERE id = :id AND user_id = :user_id
        """,
        {
            "id": item.id,
            "user_id": item.user_id,
            "content": item.content,
            "updated_at": _format_datetime(item.updated_at),
            "expires_at": _format_datetime(item.expires_at),
        },
    )


def _delete_memory(user_id: str, target_id: str) -> None:
    _database().execute(
        """
        DELETE FROM memory_items
        WHERE id = :id AND user_id = :user_id
        """,
        {
            "id": target_id,
            "user_id": user_id,
        },
    )


def _memory_snapshot(user_id: str) -> dict[MemoryType, list[MemoryItem]]:
    return {
        memory_type: _memory_snapshot_by_type(user_id, memory_type, limit)
        for memory_type, limit in _SNAPSHOT_LIMITS.items()
    }


def _memory_snapshot_by_type(user_id: str, memory_type: MemoryType, limit: int) -> list[MemoryItem]:
    now = datetime.now(UTC).replace(microsecond=0)
    rows = (
        _database()
        .execute(
            """
            SELECT id, user_id, type, content, created_at, updated_at, expires_at
            FROM memory_items
            WHERE user_id = :user_id
              AND type = :type
              AND (:type != 'context' OR expires_at IS NULL OR expires_at >= :now)
            ORDER BY updated_at DESC
            LIMIT :limit
            """,
            {
                "user_id": user_id,
                "type": memory_type,
                "now": _format_datetime(now),
                "limit": limit,
            },
        )
        .fetchall()
    )
    return [_row_to_memory_item(row) for row in rows]


def _database() -> SQLiteDatabase:
    return create_database(Settings(anthropic_api_key="").database_url)


def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _expires_at(memory_type: MemoryType, now: datetime) -> datetime | None:
    if memory_type == "context":
        return now + _CONTEXT_TTL
    return None


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"expected datetime string, got {type(value).__name__}")


def _parse_optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _parse_datetime(value)


def _row_to_memory_item(row: dict[str, Any]) -> MemoryItem:
    return MemoryItem(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        type=cast(MemoryType, row["type"]),
        content=str(row["content"]),
        created_at=_parse_datetime(row["created_at"]),
        updated_at=_parse_datetime(row["updated_at"]),
        expires_at=_parse_optional_datetime(row["expires_at"]),
    )


def _extraction_user_message(
    conversation: list[dict[str, Any]], snapshot: dict[MemoryType, list[MemoryItem]]
) -> str:
    snapshot_payload = {
        memory_type: [
            {
                "id": item.id,
                "type": item.type,
                "content": item.content,
                "updated_at": _format_datetime(item.updated_at),
                "expires_at": _format_datetime(item.expires_at),
            }
            for item in items
        ]
        for memory_type, items in snapshot.items()
    }
    return "\n\n".join(
        [
            "Existing memory snapshot:",
            json.dumps(snapshot_payload, ensure_ascii=False),
            "Conversation:",
            _conversation_to_text(conversation),
        ]
    )


def _conversation_to_text(conversation: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for message in conversation:
        role = str(message.get("role", ""))
        if role in {"system", "tool"}:
            continue
        lines.append(f"{role}: {message.get('content', '')}")
    return "\n".join(lines)
