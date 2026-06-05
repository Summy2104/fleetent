"""SQLite persistence for scheduled tasks."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database


def create(
    name: str,
    cron_expr: str,
    timezone: str,
    user_id: str,
    agent_name: str | None,
    message: str,
    source: str = "dynamic",
    session_id: str | None = None,
) -> dict[str, Any]:
    task_id = str(uuid.uuid4())
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO scheduled_tasks (
                id, name, cron_expr, timezone, user_id, agent_name,
                message, enabled, source, created_at, session_id
            )
            VALUES (
                :id, :name, :cron_expr, :timezone, :user_id, :agent_name,
                :message, 1, :source, :created_at, :session_id
            )
            """,
            {
                "id": task_id,
                "name": name,
                "cron_expr": cron_expr,
                "timezone": timezone,
                "user_id": user_id,
                "agent_name": agent_name,
                "message": message,
                "source": source,
                "created_at": now,
                "session_id": session_id,
            },
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
        "session_id": session_id,
    }


def list_tasks() -> list[dict[str, Any]]:
    rows = _database().execute("SELECT * FROM scheduled_tasks WHERE enabled = 1").fetchall()
    return [dict(row) for row in rows]


def delete(task_id: str) -> bool:
    result = _database().execute(
        "DELETE FROM scheduled_tasks WHERE id = :task_id", {"task_id": task_id}
    )
    return result.rowcount > 0


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)
