"""SQLite persistence for scheduled tasks."""

import sqlite3
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from mini_agent.user_store import DB_PATH as DB_PATH  # noqa: F401 — re-export for monkeypatching

DB_PATH = Path("data/users.db")


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                cron_expr  TEXT NOT NULL,
                timezone   TEXT NOT NULL DEFAULT 'UTC',
                user_id    TEXT NOT NULL,
                agent_name TEXT,
                message    TEXT NOT NULL,
                enabled    INTEGER NOT NULL DEFAULT 1,
                source     TEXT NOT NULL DEFAULT 'dynamic',
                created_at TEXT NOT NULL
            )
        """)


def create(
    name: str,
    cron_expr: str,
    timezone: str,
    user_id: str,
    agent_name: str | None,
    message: str,
    source: str = "dynamic",
) -> dict[str, Any]:
    _init_db()
    task_id = str(uuid.uuid4())
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as conn:
        conn.execute(
            """INSERT INTO scheduled_tasks
               (id, name, cron_expr, timezone, user_id, agent_name, message, enabled, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (task_id, name, cron_expr, timezone, user_id, agent_name, message, source, now),
        )
    return {
        "id": task_id,
        "name": name,
        "cron_expr": cron_expr,
        "timezone": timezone,
        "user_id": user_id,
        "agent_name": agent_name,
        "message": message,
        "enabled": 1,
        "source": source,
        "created_at": now,
    }


def list_tasks() -> list[dict[str, Any]]:
    _init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_tasks WHERE enabled = 1"
        ).fetchall()
    return [dict(r) for r in rows]


def delete(task_id: str) -> bool:
    _init_db()
    with _conn() as conn:
        cur = conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
    return cur.rowcount > 0
