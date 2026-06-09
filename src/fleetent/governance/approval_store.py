"""Agent-side approval store: persists tool approval requests and outcomes.

Schema owner: this module — not Alembic. Uses fleetent.db.SQLiteDatabase with
named params throughout. No platform imports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fleetent import paths
from fleetent.db import SQLiteDatabase

DB_PATH = paths.data_dir() / "fleetent.db"


def _db(db_path: Path | None = None) -> SQLiteDatabase:
    return SQLiteDatabase(path=db_path or DB_PATH)


def ensure_schema(db_path: Path | None = None) -> None:
    """Create the approvals table if it does not exist. Idempotent."""
    _db(db_path).execute(
        """
        CREATE TABLE IF NOT EXISTS approvals (
            id                TEXT PRIMARY KEY,
            session_id        TEXT NOT NULL,
            requester_user_id TEXT NOT NULL,
            risk_level        TEXT NOT NULL,
            tool_name         TEXT NOT NULL,
            tool_args         TEXT NOT NULL,
            status            TEXT NOT NULL,
            approver_actor    TEXT,
            created_at        TEXT NOT NULL,
            resolved_at       TEXT
        )
        """
    )


def insert_approval(
    *,
    id: str,
    session_id: str,
    requester_user_id: str,
    risk_level: str,
    tool_name: str,
    tool_args: str,
    created_at: str,
    db_path: Path | None = None,
) -> None:
    ensure_schema(db_path)
    _db(db_path).execute(
        """
        INSERT INTO approvals
            (id, session_id, requester_user_id, risk_level, tool_name, tool_args, status, created_at)
        VALUES
            (:id, :session_id, :requester_user_id, :risk_level, :tool_name, :tool_args, 'pending', :created_at)
        """,
        {
            "id": id,
            "session_id": session_id,
            "requester_user_id": requester_user_id,
            "risk_level": risk_level,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "created_at": created_at,
        },
    )


def update_approval(
    *,
    id: str,
    status: str,
    resolved_at: str,
    approver_actor: str | None = None,
    db_path: Path | None = None,
) -> None:
    _db(db_path).execute(
        "UPDATE approvals SET status = :status, resolved_at = :resolved_at, "
        "approver_actor = :approver_actor WHERE id = :id",
        {
            "id": id,
            "status": status,
            "resolved_at": resolved_at,
            "approver_actor": approver_actor,
        },
    )


_LIST_COLS = [
    "id", "session_id", "tool_name", "risk_level", "tool_args", "status",
    "requester_user_id", "approver_actor", "created_at", "resolved_at",
]
_SELECT = (
    "SELECT id, session_id, tool_name, risk_level, tool_args, status, "
    "requester_user_id, approver_actor, created_at, resolved_at FROM approvals"
)


def list_approvals(
    status: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    ensure_schema(db_path)
    db = _db(db_path)
    if status is not None:
        rows = db.execute(
            f"{_SELECT} WHERE status = :status ORDER BY created_at DESC",
            {"status": status},
        ).fetchall()
    else:
        rows = db.execute(
            f"{_SELECT} ORDER BY created_at DESC LIMIT 50",
        ).fetchall()
    return list(rows)


def cleanup_stale(db_path: Path | None = None) -> int:
    """Mark all pending approvals as timeout. Returns number of rows updated."""
    import datetime

    ensure_schema(db_path)
    now = datetime.datetime.now(datetime.UTC).isoformat()
    result = _db(db_path).execute(
        "UPDATE approvals SET status = 'timeout', resolved_at = :now WHERE status = 'pending'",
        {"now": now},
    )
    return result.rowcount
