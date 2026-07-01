"""Agent-side queue for managed async IM outbound delivery.

The queue lives in ``agent_state.db`` and is injected via ``set_state_db(db)`` at boot.
Managed runtimes enqueue outbound intents here; node-hosted IM edge drains and delivers
them with its live connectors. Standalone runtimes do not use this queue.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fleetent.db import ReadOnlySQLiteDatabase, SQLiteDatabase

_AnyDatabase = SQLiteDatabase | ReadOnlySQLiteDatabase

_state_db: SQLiteDatabase | None = None


def set_state_db(db: SQLiteDatabase) -> None:
    """Inject the per-agent state DB. Called once at agent boot via agent_app."""
    global _state_db
    _state_db = db


def _database() -> SQLiteDatabase:
    if _state_db is None:
        raise RuntimeError(
            "outbound_queue_store: state_db not initialized — call set_state_db(db) at boot"
        )
    return _state_db


def enqueue(
    *,
    platform: str,
    address: dict[str, Any],
    payload: dict[str, Any],
    dedup_key: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Persist one outbound delivery intent and return the inserted row."""
    row = {
        "id": str(uuid.uuid4()),
        "platform": platform,
        "address_json": json.dumps(address, ensure_ascii=False, sort_keys=True),
        "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        "dedup_key": dedup_key,
        "status": "pending",
        "attempts": 0,
        "created_at": created_at or datetime.now(UTC).isoformat(),
        "sent_at": None,
    }
    _database().execute(
        "INSERT INTO im_outbound_queue ("
        "id, platform, address_json, payload_json, dedup_key, status, attempts, created_at, sent_at"
        ") VALUES ("
        ":id, :platform, :address_json, :payload_json, :dedup_key, :status, :attempts, "
        ":created_at, :sent_at"
        ")",
        row,
    )
    return row


def list_pending(limit: int | None = None) -> list[dict[str, Any]]:
    """Return pending queue rows ordered oldest-first."""
    return list_pending_with_db(_database(), limit=limit)


def list_pending_with_db(db: _AnyDatabase, limit: int | None = None) -> list[dict[str, Any]]:
    """Return pending queue rows ordered oldest-first from an explicit DB handle."""
    sql = (
        "SELECT id, platform, address_json, payload_json, dedup_key, status, attempts, "
        "created_at, sent_at FROM im_outbound_queue WHERE status = 'pending' "
        "ORDER BY created_at ASC, id ASC"
    )
    params: dict[str, Any] = {}
    if limit is not None:
        sql += " LIMIT :limit"
        params["limit"] = limit
    rows = db.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def mark_sent(queue_id: str, *, sent_at: str | None = None) -> None:
    """Mark a queued outbound row as sent."""
    mark_sent_with_db(_database(), queue_id, sent_at=sent_at)


def mark_sent_with_db(db: SQLiteDatabase, queue_id: str, *, sent_at: str | None = None) -> None:
    """Mark a queued outbound row as sent on an explicit writable DB handle."""
    db.execute(
        "UPDATE im_outbound_queue SET status = 'sent', sent_at = :sent_at WHERE id = :id",
        {"id": queue_id, "sent_at": sent_at or datetime.now(UTC).isoformat()},
    )


def mark_failed(queue_id: str) -> None:
    """Increment attempts and keep the row pending for retry."""
    mark_failed_with_db(_database(), queue_id)


def mark_failed_with_db(db: SQLiteDatabase, queue_id: str) -> None:
    """Increment attempts and keep the row pending for retry on an explicit DB handle."""
    db.execute(
        "UPDATE im_outbound_queue SET attempts = attempts + 1, status = 'pending' WHERE id = :id",
        {"id": queue_id},
    )


def mark_dead_with_db(db: SQLiteDatabase, queue_id: str) -> None:
    """Terminally fail a row (``status='failed'``) so the drain never retries it.

    Unlike ``mark_failed_with_db`` (which keeps the row ``pending`` for retry), this is for
    permanent delivery errors (user_not_found / channel_not_found / not_in_channel): a retry
    can never succeed, so leaving it pending only burns a delivery attempt every interval
    forever (AAA-8204). ``list_pending_with_db`` filters on ``status='pending'``, so a
    ``failed`` row is excluded from future drains.
    """
    db.execute(
        "UPDATE im_outbound_queue SET attempts = attempts + 1, status = 'failed' WHERE id = :id",
        {"id": queue_id},
    )
