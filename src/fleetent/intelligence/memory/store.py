"""SQLite access for User Memory records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.intelligence.memory.models import (
    MemoryCompactionCandidate,
    MemoryItem,
    MemoryMaintenancePolicy,
    MemoryType,
)

SNAPSHOT_LIMITS: dict[MemoryType, int] = {
    "identity": 20,
    "preferences": 30,
    "context": 20,
}


def get_user_memory(user_id: str, memory_id: str) -> MemoryItem | None:
    row = (
        database()
        .execute(
            """
            SELECT id, user_id, type, content, created_at, updated_at, expires_at, namespace
            FROM memory_items
            WHERE user_id = :user_id AND id = :id
            """,
            {"user_id": user_id, "id": memory_id},
        )
        .fetchone()
    )
    if row is None:
        return None
    return row_to_memory_item(row)


def insert_memory(item: MemoryItem) -> None:
    database().execute(
        """
        INSERT INTO memory_items (
            id, user_id, type, content, created_at, updated_at, expires_at, namespace
        )
        VALUES (
            :id, :user_id, :type, :content, :created_at, :updated_at, :expires_at, :namespace
        )
        """,
        {
            "id": item.id,
            "user_id": item.user_id,
            "type": item.type,
            "content": item.content,
            "created_at": format_datetime(item.created_at),
            "updated_at": format_datetime(item.updated_at),
            "expires_at": format_datetime(item.expires_at),
            "namespace": item.namespace,
        },
    )


def update_memory(item: MemoryItem) -> None:
    database().execute(
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
            "updated_at": format_datetime(item.updated_at),
            "expires_at": format_datetime(item.expires_at),
        },
    )


def delete_memory(user_id: str, target_id: str) -> None:
    database().execute(
        """
        DELETE FROM memory_items
        WHERE id = :id AND user_id = :user_id
        """,
        {
            "id": target_id,
            "user_id": user_id,
        },
    )


def memory_snapshot(user_id: str, namespace: str = "default") -> dict[MemoryType, list[MemoryItem]]:
    return {
        memory_type: memory_snapshot_by_type(user_id, memory_type, limit, namespace)
        for memory_type, limit in SNAPSHOT_LIMITS.items()
    }


def memory_snapshot_by_type(
    user_id: str, memory_type: MemoryType, limit: int, namespace: str = "default"
) -> list[MemoryItem]:
    now = datetime.now(UTC).replace(microsecond=0)
    rows = (
        database()
        .execute(
            """
            SELECT id, user_id, type, content, created_at, updated_at, expires_at, namespace
            FROM memory_items
            WHERE user_id = :user_id
              AND namespace = :namespace
              AND type = :type
              AND (:type != 'context' OR expires_at IS NULL OR expires_at >= :now)
            ORDER BY updated_at DESC
            LIMIT :limit
            """,
            {
                "user_id": user_id,
                "namespace": namespace,
                "type": memory_type,
                "now": format_datetime(now),
                "limit": limit,
            },
        )
        .fetchall()
    )
    return [row_to_memory_item(row) for row in rows]


def memory_items_by_ids(
    user_id: str, ids: list[str], namespace: str = "default"
) -> dict[str, MemoryItem]:
    if not ids:
        return {}
    placeholders = ", ".join(f":id_{index}" for index in range(len(ids)))
    params = {f"id_{index}": id for index, id in enumerate(ids)}
    params["user_id"] = user_id
    params["namespace"] = namespace
    rows = (
        database()
        .execute(
            f"""
            SELECT id, user_id, type, content, created_at, updated_at, expires_at, namespace
            FROM memory_items
            WHERE user_id = :user_id AND namespace = :namespace AND id IN ({placeholders})
            """,
            params,
        )
        .fetchall()
    )
    return {str(row["id"]): row_to_memory_item(row) for row in rows}


def indexable_memory_rows(user_id: str) -> list[dict[str, Any]]:
    now = datetime.now(UTC).replace(microsecond=0)
    return (
        database()
        .execute(
            """
            SELECT id, type, content
            FROM memory_items
            WHERE user_id = :user_id
              AND (expires_at IS NULL OR expires_at >= :now)
            ORDER BY updated_at ASC, id ASC
            """,
            {
                "user_id": user_id,
                "now": format_datetime(now),
            },
        )
        .fetchall()
    )


def expired_context_ids(user_id: str) -> list[str]:
    now = datetime.now(UTC).replace(microsecond=0)
    rows = (
        database()
        .execute(
            """
            SELECT id
            FROM memory_items
            WHERE user_id = :user_id
              AND type = 'context'
              AND expires_at IS NOT NULL
              AND expires_at < :now
            ORDER BY updated_at ASC, id ASC
            """,
            {"user_id": user_id, "now": format_datetime(now)},
        )
        .fetchall()
    )
    return [str(row["id"]) for row in rows]


def over_limit_ids(user_id: str, policy: MemoryMaintenancePolicy) -> list[str]:
    result: list[str] = []
    limits: dict[MemoryType, int] = {
        "identity": policy.max_identity,
        "preferences": policy.max_preferences,
        "context": policy.max_context,
    }
    for memory_type, limit in limits.items():
        rows = (
            database()
            .execute(
                """
                SELECT id
                FROM memory_items
                WHERE user_id = :user_id AND type = :type
                ORDER BY updated_at DESC, id ASC
                """,
                {"user_id": user_id, "type": memory_type},
            )
            .fetchall()
        )
        result.extend(str(row["id"]) for row in rows[limit:])
    return result


def duplicate_compaction_candidates(user_id: str) -> list[MemoryCompactionCandidate]:
    rows = (
        database()
        .execute(
            """
            SELECT id, type, content, updated_at
            FROM memory_items
            WHERE user_id = :user_id
            ORDER BY type ASC, updated_at DESC, id ASC
            """,
            {"user_id": user_id},
        )
        .fetchall()
    )
    groups: dict[tuple[MemoryType, str], list[dict[str, Any]]] = {}
    for row in rows:
        memory_type = cast(MemoryType, row["type"])
        key = (memory_type, normalize_memory_content(str(row["content"])))
        groups.setdefault(key, []).append(row)

    candidates: list[MemoryCompactionCandidate] = []
    for (memory_type, _normalized), items in groups.items():
        if len(items) < 2:
            continue
        canonical = items[0]
        duplicates = items[1:]
        candidates.append(
            MemoryCompactionCandidate(
                type=memory_type,
                canonical_id=str(canonical["id"]),
                duplicate_ids=[str(item["id"]) for item in duplicates],
                reason="duplicate_normalized_content",
            )
        )
    return candidates


def database() -> SQLiteDatabase:
    return create_database(Settings(anthropic_api_key="").database_url)


def format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"expected datetime string, got {type(value).__name__}")


def parse_optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return parse_datetime(value)


def row_to_memory_item(row: dict[str, Any]) -> MemoryItem:
    return MemoryItem(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        type=cast(MemoryType, row["type"]),
        content=str(row["content"]),
        created_at=parse_datetime(row["created_at"]),
        updated_at=parse_datetime(row["updated_at"]),
        expires_at=parse_optional_datetime(row["expires_at"]),
        namespace=str(row["namespace"]) if row.get("namespace") is not None else "default",
    )


def normalize_memory_content(content: str) -> str:
    return " ".join(content.split()).casefold()
