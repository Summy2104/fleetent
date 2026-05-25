"""Human-in-the-loop permission gate.

Tools annotated with a risk_level pause execution until an out-of-band approver
resolves the request (or the timeout elapses). State is persisted to the
`approvals` SQLite table so an audit trail survives restarts.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any, Literal

from fleetent.user_store import (
    DB_PATH as DB_PATH,  # noqa: F401 — re-export for test monkeypatching
)
from fleetent.user_store import (
    _conn,
)

logger = logging.getLogger(__name__)

ApprovalResult = Literal["approved", "rejected", "timeout"]


class PermissionGate:
    def __init__(self, medium_timeout: float = 300.0, high_timeout: float = 3600.0) -> None:
        self._medium_timeout = medium_timeout
        self._high_timeout = high_timeout
        self._events: dict[str, asyncio.Event] = {}
        self._decisions: dict[str, str] = {}

    async def request_approval(
        self,
        approval_id: str,
        risk_level: str,
        tool_name: str,
        tool_args: dict[str, Any],
        requester_user_id: str,
        reply_func: Callable[..., Coroutine[Any, Any, None]],
    ) -> ApprovalResult:
        _init_db()
        now = datetime.datetime.now(datetime.UTC).isoformat()
        with _conn() as conn:
            conn.execute(
                "INSERT INTO approvals "
                "(id, session_id, requester_user_id, risk_level, tool_name, "
                "tool_args, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
                (
                    approval_id,
                    "",
                    requester_user_id,
                    risk_level,
                    tool_name,
                    json.dumps(tool_args),
                    now,
                ),
            )

        event = asyncio.Event()
        self._events[approval_id] = event

        timeout = self._medium_timeout if risk_level == "medium" else self._high_timeout
        await reply_func(
            f"Tool `{tool_name}` requires approval (risk: {risk_level}). "
            f"Approval ID: {approval_id}"
        )

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            decision = self._decisions.get(approval_id, "rejected")
        except TimeoutError:
            decision = "timeout"

        resolved_at = datetime.datetime.now(datetime.UTC).isoformat()
        with _conn() as conn:
            conn.execute(
                "UPDATE approvals SET status = ?, resolved_at = ? WHERE id = ?",
                (decision, resolved_at, approval_id),
            )

        self._events.pop(approval_id, None)
        self._decisions.pop(approval_id, None)
        logger.info(
            "approval_resolved id=%s tool=%s risk=%s decision=%s",
            approval_id,
            tool_name,
            risk_level,
            decision,
        )
        return decision  # type: ignore[return-value]

    async def resolve(
        self,
        approval_id: str,
        decision: Literal["approved", "rejected"],
        approver_user_id: str,
    ) -> bool:
        """Resolve an approval request. Returns True if the request was found, False if expired/unknown."""
        event = self._events.get(approval_id)
        if event is None:
            return False
        with _conn() as conn:
            conn.execute(
                "UPDATE approvals SET approver_user_id = ? WHERE id = ?",
                (approver_user_id, approval_id),
            )
        self._decisions[approval_id] = decision
        event.set()
        return True


_default_gate: PermissionGate = PermissionGate()


def list_approvals(status: str | None = None) -> list[dict]:  # type: ignore[type-arg]
    """Return approvals from DB, optionally filtered by status."""
    _init_db()
    with _conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT id, tool_name, risk_level, tool_args, status, "
                "requester_user_id, approver_user_id, created_at, resolved_at "
                "FROM approvals WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, tool_name, risk_level, tool_args, status, "
                "requester_user_id, approver_user_id, created_at, resolved_at "
                "FROM approvals ORDER BY created_at DESC LIMIT 50",
            ).fetchall()
    cols = ["id", "tool_name", "risk_level", "tool_args", "status",
            "requester_user_id", "approver_user_id", "created_at", "resolved_at"]
    return [dict(zip(cols, r)) for r in rows]


def cleanup_stale_approvals() -> None:
    """Mark all pending approvals as timeout. Call at server startup after a restart."""
    _init_db()
    now = datetime.datetime.now(datetime.UTC).isoformat()
    with _conn() as conn:
        count = conn.execute(
            "UPDATE approvals SET status = 'timeout', resolved_at = ? WHERE status = 'pending'",
            (now,),
        ).rowcount
    if count:
        logger.info("startup_cleanup stale_approvals_marked_timeout count=%d", count)


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS approvals (
                id                TEXT PRIMARY KEY,
                session_id        TEXT NOT NULL,
                requester_user_id TEXT NOT NULL,
                risk_level        TEXT NOT NULL,
                tool_name         TEXT NOT NULL,
                tool_args         TEXT NOT NULL,
                status            TEXT NOT NULL,
                approver_user_id  TEXT,
                created_at        TEXT NOT NULL,
                resolved_at       TEXT
            )"""
        )
