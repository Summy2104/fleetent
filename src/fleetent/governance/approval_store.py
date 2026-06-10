"""Agent-side approval store: persists tool approval requests and outcomes.

Schema owner: agent_state.db via per-agent MIGRATIONS (v12).  Connection is
injected via set_state_db() at agent boot — no ensure_schema, no DB_PATH.
Uses named parameters throughout.  No platform imports.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Union

from fleetent.db import ReadOnlySQLiteDatabase, SQLiteDatabase

if TYPE_CHECKING:
    pass

_AnyDatabase = Union[SQLiteDatabase, ReadOnlySQLiteDatabase]

_state_db: SQLiteDatabase | None = None


def set_state_db(db: SQLiteDatabase) -> None:
    """Inject the per-agent state DB.  Called once at agent boot."""
    global _state_db
    _state_db = db


def database() -> SQLiteDatabase:
    if _state_db is None:
        raise RuntimeError(
            "approval_store: state_db not initialized — call set_state_db(db) at boot"
        )
    return _state_db


def insert_approval(
    *,
    id: str,
    session_id: str,
    requester_user_id: str,
    risk_level: str,
    tool_name: str,
    tool_args: str,
    created_at: str,
) -> None:
    database().execute(
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
) -> None:
    database().execute(
        "UPDATE approvals SET status = :status, resolved_at = :resolved_at, "
        "approver_actor = :approver_actor WHERE id = :id",
        {
            "id": id,
            "status": status,
            "resolved_at": resolved_at,
            "approver_actor": approver_actor,
        },
    )


_SELECT = (
    "SELECT id, session_id, tool_name, risk_level, tool_args, status, "
    "requester_user_id, approver_actor, created_at, resolved_at FROM approvals"
)


def list_approvals(
    status: str | None = None,
) -> list[dict[str, Any]]:
    db = database()
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


def list_approvals_with_db(
    db: "_AnyDatabase",
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Read-only variant of list_approvals that accepts an explicit DB handle.

    Used by platform read projection to read from agent DBs via read-only connections
    without touching the module-level _state_db.
    """
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


def cleanup_stale() -> int:
    """Mark all pending approvals as timeout. Returns number of rows updated."""
    now = datetime.datetime.now(datetime.UTC).isoformat()
    result = database().execute(
        "UPDATE approvals SET status = 'timeout', resolved_at = :now WHERE status = 'pending'",
        {"now": now},
    )
    return result.rowcount
