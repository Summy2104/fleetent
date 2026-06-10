"""Agent-side approval store: persists tool approval requests and outcomes.

Schema owner: this module — not Alembic. Uses fleetent.db.SQLiteDatabase with
named params throughout. No platform imports.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fleetent import paths
from fleetent.db import SQLiteDatabase
from fleetent.structured_logging import get_logger

DB_PATH = paths.data_dir() / "fleetent.db"

_logger = get_logger("governance.approval_store")


def _db(db_path: Path | None = None) -> SQLiteDatabase:
    return SQLiteDatabase(path=db_path or DB_PATH)


def _approvals_has_column(db: SQLiteDatabase, column: str) -> bool:
    """Whether the approvals table already has *column* (via PRAGMA table_info)."""
    rows = db.execute("PRAGMA table_info(approvals)").fetchall()
    return any(row["name"] == column for row in rows)


def _add_approver_actor_column(db: SQLiteDatabase) -> None:
    """ALTER in the approver_actor column. Caller guards on absence."""
    db.execute("ALTER TABLE approvals ADD COLUMN approver_actor TEXT")


def ensure_schema(db_path: Path | None = None) -> None:
    """Create the approvals table if absent; self-heal a legacy column drift.

    存量部署的 approvals 表是旧形态（含 ``approver_user_id``、无 ``approver_actor``），
    而 ``update_approval`` 写 ``approver_actor`` 会抛 ``no such column``。``CREATE TABLE
    IF NOT EXISTS`` 对已存在的表不补列，故此处探测并 ``ALTER`` 补列，再从旧列回填——
    补列只发生在旧形态表上（``approver_user_id`` 必在），新建/新形态库为 no-op。

    本自愈为过渡 hotfix：approvals 整体迁入 per-agent 嵌入式迁移（per-agent-approvals-lib）
    后随 ``ensure_schema`` 一并退役。
    """
    db = _db(db_path)
    db.execute(
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
    if _approvals_has_column(db, "approver_actor"):
        return
    try:
        _add_approver_actor_column(db)
    except sqlite3.OperationalError as exc:
        # 并发竞态：另一进程已补列。识别该特定错误为「已自愈」，其它异常照常抛出。
        if "duplicate column" in str(exc).lower():
            _logger.info("approvals_approver_actor_concurrent_add")
            return
        raise
    # 补列成功 ⇒ 旧形态表 ⇒ approver_user_id 必在；仍防御性 guard，避免异形表崩溃。
    if _approvals_has_column(db, "approver_user_id"):
        db.execute(
            "UPDATE approvals SET approver_actor = approver_user_id WHERE approver_actor IS NULL"
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
            (id, session_id, requester_user_id, risk_level, tool_name,
             tool_args, status, created_at)
        VALUES
            (:id, :session_id, :requester_user_id, :risk_level, :tool_name,
             :tool_args, 'pending', :created_at)
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
    "id",
    "session_id",
    "tool_name",
    "risk_level",
    "tool_args",
    "status",
    "requester_user_id",
    "approver_actor",
    "created_at",
    "resolved_at",
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
