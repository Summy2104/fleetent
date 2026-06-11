"""SQLite persistence for scheduled tasks.

Agent-owned store: schema is created by the unified agent_state.db embedded
migrations (AGENT_STATE_MIGRATIONS v27). Access the table through the database
injected via ``set_state_db(db)`` — the same agent_state.db handle used by
traces, reflection, memory, and approvals. No platform imports.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fleetent.db import SQLiteDatabase

_state_db: SQLiteDatabase | None = None


def set_state_db(db: SQLiteDatabase) -> None:
    """Inject the per-agent state DB. Called once at agent boot via agent_app."""
    global _state_db
    _state_db = db


def _database() -> SQLiteDatabase:
    if _state_db is None:
        raise RuntimeError(
            "schedule_store: state_db not initialized — call set_state_db(db) at boot"
        )
    return _state_db


def create(
    name: str,
    cron_expr: str | None = None,
    timezone: str = "UTC",
    user_id: str = "default",
    message: str = "",
    source: str = "dynamic",
    session_id: str | None = None,
    *,
    schedule_kind: str = "cron",
    run_at: str | None = None,
    interval_seconds: int | None = None,
    anchor: str | None = None,
    origin: dict[str, Any] | None = None,
    deliver: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a scheduled task and return it as a dict.

    Positional params: name, cron_expr, timezone, user_id, message, source, session_id.
    The ``schedule_kind`` and one-shot/interval/delivery fields are keyword-only.
    """
    task_id = str(uuid.uuid4())
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {
        "id": task_id,
        "name": name,
        "schedule_kind": schedule_kind,
        "cron_expr": cron_expr,
        "run_at": run_at,
        "interval_seconds": interval_seconds,
        "anchor": anchor,
        "timezone": timezone,
        "user_id": user_id,
        "message": message,
        "session_id": session_id,
        "origin": json.dumps(origin) if origin is not None else None,
        "deliver": json.dumps(deliver) if deliver is not None else None,
        "enabled": 1,
        "source": source,
        "created_at": now,
        "last_run_at": None,
        "last_status": None,
        "last_error": None,
        "next_run_at": None,
    }
    with _database().transaction() as conn:
        conn.execute(
            "INSERT INTO scheduled_tasks ("
            "id, name, schedule_kind, cron_expr, run_at, interval_seconds, anchor, "
            "timezone, user_id, message, session_id, origin, deliver, "
            "enabled, source, created_at, last_run_at, last_status, last_error, next_run_at"
            ") VALUES ("
            ":id, :name, :schedule_kind, :cron_expr, :run_at, :interval_seconds, :anchor, "
            ":timezone, :user_id, :message, :session_id, :origin, :deliver, "
            ":enabled, :source, :created_at, :last_run_at, :last_status, :last_error, :next_run_at"
            ")",
            row,
        )
    return _decode(row)


def list_tasks(include_disabled: bool = False) -> list[dict[str, Any]]:
    """Return tasks as dicts. By default only enabled tasks (the scheduler load set)."""
    sql = "SELECT * FROM scheduled_tasks"
    if not include_disabled:
        sql += " WHERE enabled = 1"
    rows = _database().execute(sql).fetchall()
    return [_decode(dict(row)) for row in rows]


def get(task_id: str) -> dict[str, Any] | None:
    """Return a single task by id, or None."""
    row = _database().execute(
        "SELECT * FROM scheduled_tasks WHERE id = :id", {"id": task_id}
    ).fetchone()
    return _decode(dict(row)) if row is not None else None


def set_enabled(task_id: str, enabled: bool) -> bool:
    """Toggle a task's enabled flag (pause/resume). Returns True if a row matched."""
    result = _database().execute(
        "UPDATE scheduled_tasks SET enabled = :enabled WHERE id = :id",
        {"enabled": 1 if enabled else 0, "id": task_id},
    )
    return result.rowcount > 0


def update_run_state(
    task_id: str,
    *,
    last_run_at: str | None = None,
    last_status: str | None = None,
    last_error: str | None = None,
    next_run_at: str | None = None,
) -> None:
    """Write back observability/runtime-state columns after a fire."""
    _database().execute(
        "UPDATE scheduled_tasks SET last_run_at = :last_run_at, last_status = :last_status, "
        "last_error = :last_error, next_run_at = :next_run_at WHERE id = :id",
        {
            "id": task_id,
            "last_run_at": last_run_at,
            "last_status": last_status,
            "last_error": last_error,
            "next_run_at": next_run_at,
        },
    )


def delete(task_id: str) -> bool:
    result = _database().execute(
        "DELETE FROM scheduled_tasks WHERE id = :task_id", {"task_id": task_id}
    )
    return result.rowcount > 0


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    """Deserialize JSON columns (origin/deliver) back into dicts for callers."""
    out = dict(row)
    for key in ("origin", "deliver"):
        val = out.get(key)
        if isinstance(val, str):
            out[key] = json.loads(val)
    return out
