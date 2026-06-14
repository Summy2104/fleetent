"""Compatibility facade for tool-call approvals backed by approval_requests."""

from __future__ import annotations

import datetime
import json
from typing import Any

from fleetent.db import ReadOnlySQLiteDatabase, SQLiteDatabase
from fleetent.governance import approval_request_store
from fleetent.session import manager as session_mgr

_AnyDatabase = SQLiteDatabase | ReadOnlySQLiteDatabase

_state_db: SQLiteDatabase | None = None


def set_state_db(db: SQLiteDatabase) -> None:
    """Inject the per-agent state DB. Called once at agent boot."""
    global _state_db
    _state_db = db
    approval_request_store.set_state_db(db)


def database() -> SQLiteDatabase:
    if _state_db is None:
        raise RuntimeError(
            "approval_store: state_db not initialized — call set_state_db(db) at boot"
        )
    approval_request_store.set_state_db(_state_db)
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
    approval_request_store.set_state_db(database())
    approval_request_store.create_request(
        id=id,
        subject_type="tool_call",
        subject_id=session_id or id,
        requester_user_id=requester_user_id,
        risk=risk_level,
        routing_key=tool_name,
        created_at=created_at,
    )


def update_approval(
    *,
    id: str,
    status: str,
    resolved_at: str,
    approver_user_id: str | None = None,
) -> None:
    approval_request_store.set_state_db(database())
    approval_request_store.decide_request(
        id=id,
        status="expired" if status == "timeout" else status,
        decided_at=resolved_at,
        approver_user_id=approver_user_id,
    )


def _pending_entry(session_id: str, approval_id: str) -> dict[str, object] | None:
    if not session_id:
        return None
    path = session_mgr.SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    meta = payload.get("meta") or {}
    pending = meta.get("pending_approvals") or {}
    entry = pending.get(approval_id)
    return dict(entry) if isinstance(entry, dict) else None


def _row_to_legacy(row: dict[str, Any]) -> dict[str, Any]:
    session_id = str(row["subject_id"] or "")
    pending = _pending_entry(session_id, str(row["id"]))
    return {
        "id": row["id"],
        "session_id": session_id,
        "tool_name": row["routing_key"],
        "risk_level": row["risk"],
        "tool_args": json.dumps(pending.get("tool_args", {})) if pending is not None else "{}",
        "status": "timeout" if row["status"] == "expired" else row["status"],
        "requester_user_id": row["requester_user_id"],
        "approver_user_id": row["approver_user_id"],
        "created_at": row["created_at"],
        "resolved_at": row["decided_at"],
    }


def get_approval(approval_id: str) -> dict[str, Any] | None:
    approval_request_store.set_state_db(database())
    row = approval_request_store.get_request(approval_id)
    if row is None or row.get("subject_type") != "tool_call":
        return None
    return _row_to_legacy(row)


def list_approvals(status: str | None = None) -> list[dict[str, Any]]:
    approval_request_store.set_state_db(database())
    rows = approval_request_store.list_requests(
        status="expired" if status == "timeout" else status,
        subject_type="tool_call",
    )
    return [_row_to_legacy(row) for row in rows]


def list_approvals_with_db(
    db: _AnyDatabase,
    status: str | None = None,
) -> list[dict[str, Any]]:
    rows = approval_request_store.list_requests_with_db(
        db,
        status="expired" if status == "timeout" else status,
        subject_type="tool_call",
    )
    return [_row_to_legacy(row) for row in rows]


def cleanup_stale() -> int:
    now = datetime.datetime.now(datetime.UTC).isoformat()
    return approval_request_store.expire_pending_requests(now=now)
