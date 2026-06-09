"""SQLite persistence for scheduled tasks.

Agent-owned store (agent-owned-scheduled-tasks): the schema is created on demand
via ``ensure_schema`` (idempotent ``CREATE TABLE`` ... ``IF NOT EXISTS``) so a
standalone ``fleetent agent run`` works without platform migrations — joining the
agent-side dual-authority tables (traces, memory_items). The platform DB keeps the
same table via Alembic; the DDL here MUST match the Alembic head (drift guard). No
platform imports.

The database is resolved from ``DATABASE_URL`` (``Settings``), which ``agent_app``
redirects to the per-agent ``data/`` dir on standalone boot — so the same code
targets the agent DB in an agent process and the platform DB in the platform process.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

# Single source for the table DDL so ensure_schema and the Alembic migration stay in
# sync (drift guard). ``agent_name`` is retained (nullable) for the platform
# stats-report scheduler, which routes a fired job to a named agent; the agent
# runtime leaves it NULL (one agent per process).
_TABLE_DDL = (
    "CREATE TABLE IF NOT EXISTS scheduled_tasks ("
    "id TEXT PRIMARY KEY, "
    "name TEXT, "
    "schedule_kind TEXT NOT NULL DEFAULT 'cron', "
    "cron_expr TEXT, "
    "run_at TEXT, "
    "interval_seconds INTEGER, "
    "anchor TEXT, "
    "timezone TEXT, "
    "user_id TEXT, "
    "agent_name TEXT, "
    "message TEXT, "
    "session_id TEXT, "
    "origin TEXT, "
    "deliver TEXT, "
    "enabled INTEGER NOT NULL DEFAULT 1, "
    "source TEXT, "
    "created_at TEXT, "
    "last_run_at TEXT, "
    "last_status TEXT, "
    "last_error TEXT, "
    "next_run_at TEXT"
    ")"
)


def ensure_schema(db: SQLiteDatabase) -> None:
    """Create the scheduled_tasks table if absent. Idempotent (agent-side schema owner)."""
    with db.transaction() as conn:
        conn.execute(_TABLE_DDL)


def create(
    name: str,
    cron_expr: str | None = None,
    timezone: str = "UTC",
    user_id: str = "default",
    agent_name: str | None = None,
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

    Positional params stay backward-compatible with the platform stats scheduler and
    admin CLI (name, cron_expr, timezone, user_id, agent_name, message, source). The
    ``schedule_kind`` and one-shot/interval/delivery fields are keyword-only.
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
        "agent_name": agent_name,
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
    db = _database()
    ensure_schema(db)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO scheduled_tasks ("
            "id, name, schedule_kind, cron_expr, run_at, interval_seconds, anchor, "
            "timezone, user_id, agent_name, message, session_id, origin, deliver, "
            "enabled, source, created_at, last_run_at, last_status, last_error, next_run_at"
            ") VALUES ("
            ":id, :name, :schedule_kind, :cron_expr, :run_at, :interval_seconds, :anchor, "
            ":timezone, :user_id, :agent_name, :message, :session_id, :origin, :deliver, "
            ":enabled, :source, :created_at, :last_run_at, :last_status, :last_error, :next_run_at"
            ")",
            row,
        )
    return _decode(row)


def list_tasks(include_disabled: bool = False) -> list[dict[str, Any]]:
    """Return tasks as dicts. By default only enabled tasks (the scheduler load set)."""
    db = _database()
    ensure_schema(db)
    sql = "SELECT * FROM scheduled_tasks"
    if not include_disabled:
        sql += " WHERE enabled = 1"
    rows = db.execute(sql).fetchall()
    return [_decode(dict(row)) for row in rows]


def get(task_id: str) -> dict[str, Any] | None:
    """Return a single task by id, or None."""
    db = _database()
    ensure_schema(db)
    row = db.execute("SELECT * FROM scheduled_tasks WHERE id = :id", {"id": task_id}).fetchone()
    return _decode(dict(row)) if row is not None else None


def set_enabled(task_id: str, enabled: bool) -> bool:
    """Toggle a task's enabled flag (pause/resume). Returns True if a row matched."""
    db = _database()
    ensure_schema(db)
    result = db.execute(
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
    db = _database()
    ensure_schema(db)
    db.execute(
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
    db = _database()
    ensure_schema(db)
    result = db.execute("DELETE FROM scheduled_tasks WHERE id = :task_id", {"task_id": task_id})
    return result.rowcount > 0


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    """Deserialize JSON columns (origin/deliver) back into dicts for callers."""
    out = dict(row)
    for key in ("origin", "deliver"):
        val = out.get(key)
        if isinstance(val, str):
            out[key] = json.loads(val)
    return out


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)
