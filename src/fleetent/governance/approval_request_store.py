"""Agent-side approval-request store for unified approval lifecycles."""

from __future__ import annotations

import datetime
from typing import Any

from fleetent.db import ReadOnlySQLiteDatabase, SQLiteDatabase

_AnyDatabase = SQLiteDatabase | ReadOnlySQLiteDatabase

_state_db: SQLiteDatabase | None = None

_SELECT = (
    "SELECT id, subject_type, subject_id, requester_user_id, risk, status, "
    "approver_user_id, decided_at, reason, routing_key, created_at, expires_at "
    "FROM approval_requests"
)


def set_state_db(db: SQLiteDatabase) -> None:
    """Inject the per-agent state DB. Called once at agent boot."""
    global _state_db
    _state_db = db


def database() -> SQLiteDatabase:
    if _state_db is None:
        raise RuntimeError(
            "approval_request_store: state_db not initialized — call set_state_db(db) at boot"
        )
    return _state_db


def create_request(
    *,
    id: str,
    subject_type: str,
    subject_id: str,
    requester_user_id: str | None,
    risk: str,
    routing_key: str,
    created_at: str,
    expires_at: str | None = None,
) -> None:
    database().execute(
        """
        INSERT OR IGNORE INTO approval_requests (
            id, subject_type, subject_id, requester_user_id, risk, status,
            routing_key, created_at, expires_at
        )
        VALUES (
            :id, :subject_type, :subject_id, :requester_user_id, :risk, 'pending',
            :routing_key, :created_at, :expires_at
        )
        """,
        {
            "id": id,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "requester_user_id": requester_user_id,
            "risk": risk,
            "routing_key": routing_key,
            "created_at": created_at,
            "expires_at": expires_at,
        },
    )


def decide_request(
    *,
    id: str,
    status: str,
    decided_at: str,
    approver_user_id: str | None = None,
    reason: str | None = None,
) -> None:
    database().execute(
        """
        UPDATE approval_requests
        SET status = :status,
            decided_at = :decided_at,
            approver_user_id = :approver_user_id,
            reason = :reason
        WHERE id = :id
        """,
        {
            "id": id,
            "status": status,
            "decided_at": decided_at,
            "approver_user_id": approver_user_id,
            "reason": reason,
        },
    )


def get_request(request_id: str) -> dict[str, Any] | None:
    row = (
        database()
        .execute(
            f"{_SELECT} WHERE id = :id",
            {"id": request_id},
        )
        .fetchone()
    )
    return dict(row) if row is not None else None


def list_requests(
    *,
    status: str | None = None,
    subject_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return list_requests_with_db(
        database(),
        status=status,
        subject_type=subject_type,
        limit=limit,
    )


def list_requests_with_db(
    db: _AnyDatabase,
    *,
    status: str | None = None,
    subject_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    if status is not None:
        where.append("status = :status")
        params["status"] = status
    if subject_type is not None:
        where.append("subject_type = :subject_type")
        params["subject_type"] = subject_type

    query = _SELECT
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY created_at DESC LIMIT :limit"
    return list(db.execute(query, params).fetchall())


def expire_pending_requests(*, now: str | None = None) -> int:
    decided_at = now or datetime.datetime.now(datetime.UTC).isoformat()
    result = database().execute(
        """
        UPDATE approval_requests
        SET status = 'expired',
            decided_at = :decided_at
        WHERE status = 'pending'
        """,
        {"decided_at": decided_at},
    )
    return result.rowcount
