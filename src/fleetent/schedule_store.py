"""SQLite persistence for scheduled tasks.

Agent-owned store: schema is created by the unified agent_state.db embedded
migrations (AGENT_STATE_MIGRATIONS v27). Access the table through the database
injected via ``set_state_db(db)`` — the same agent_state.db handle used by
traces, reflection, memory, and approvals. No platform imports.
"""

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from fleetent.db import SQLiteDatabase

logger = logging.getLogger(__name__)

_state_db: SQLiteDatabase | None = None

# schedule-create-delivery-guardrail: send/delivery imperatives that, when embedded in a
# `generate` task's message WITHOUT an explicit `deliver`, signal the recurring footgun
# (delivery falls back to the creation channel + the model self-delivers). Conservative by
# design: only clear "send to a recipient" phrasings.
_SEND_IMPERATIVE_RE = re.compile(
    r"私信|发送给|发送到|发给|推送给|发到|转发给|send\s+to|\bDM\b", re.IGNORECASE
)


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
    task_type: str = "generate",
    notify_text: str | None = None,
) -> dict[str, Any]:
    """Persist a scheduled task and return it as a dict.

    Positional params: name, cron_expr, timezone, user_id, message, source, session_id.
    The ``schedule_kind`` and one-shot/interval/delivery fields are keyword-only.

    ``task_type`` (typed-scheduled-task-delivery) selects fire behavior:
    - ``notify``   — scheduler sends the frozen ``notify_text`` verbatim, no agent run.
    - ``generate`` — agent produces the notification body, scheduler delivers it (default).
    - ``action``   — agent acts (sends via its own tools); the scheduler never broadcasts.
    A ``notify`` task requires ``notify_text`` and a resolvable delivery target; ``generate``
    / ``action`` require ``message``.
    """
    if schedule_kind not in ("cron", "once", "interval"):
        raise ValueError(f"invalid schedule_kind: {schedule_kind!r} (cron/once/interval)")
    if task_type not in ("notify", "generate", "action"):
        raise ValueError(f"invalid task_type: {task_type!r} (notify/generate/action)")
    if task_type == "notify":
        if not notify_text:
            raise ValueError("notify task requires notify_text (the frozen notification copy)")
        if deliver is None and origin is None:
            raise ValueError("notify task requires a delivery target (deliver or origin)")
    elif not message:
        raise ValueError(f"{task_type} task requires message (the agent prompt)")
    # schedule-create-delivery-guardrail: a `generate` task with no explicit `deliver` whose
    # message embeds a send instruction is the recurring footgun — deliver falls back to the
    # creation channel AND the model self-delivers (mis-routed/duplicate). Steer to an explicit
    # delivery target (notify_target) or `action`. Conservative: all three conditions required.
    if (
        task_type == "generate"
        and deliver is None
        and message
        and _SEND_IMPERATIVE_RE.search(message)
    ):
        raise ValueError(
            "generate 任务的回复由调度器投递到 deliver/origin 目标，不要在 message 里写"
            "「发送给X / 私信X」等发送指令（否则会投错地方或重复发送）。请用 notify_target"
            "/notify_target_type 指定投递目标，或改用 task_type=action 让 agent 自己发送。"
        )
    task_id = str(uuid.uuid4())
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {
        "id": task_id,
        "name": name,
        "task_type": task_type,
        "notify_text": notify_text,
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
            "id, name, task_type, notify_text, schedule_kind, cron_expr, run_at, "
            "interval_seconds, anchor, "
            "timezone, user_id, message, session_id, origin, deliver, "
            "enabled, source, created_at, last_run_at, last_status, last_error, next_run_at"
            ") VALUES ("
            ":id, :name, :task_type, :notify_text, :schedule_kind, :cron_expr, :run_at, "
            ":interval_seconds, :anchor, "
            ":timezone, :user_id, :message, :session_id, :origin, :deliver, "
            ":enabled, :source, :created_at, :last_run_at, :last_status, :last_error, :next_run_at"
            ")",
            row,
        )
    return _decode(row)


def list_tasks(include_disabled: bool = False) -> list[dict[str, Any]]:
    """Return tasks as dicts. By default only enabled tasks (the scheduler load set).

    A single row with corrupt JSON columns (origin/deliver) is skipped and logged
    rather than raising for the whole table (cron-hardening F6.1) — one bad row
    (a hand-edit, a partial write) must never wedge the tick loop for every task.
    """
    sql = "SELECT * FROM scheduled_tasks"
    if not include_disabled:
        sql += " WHERE enabled = 1"
    rows = _database().execute(sql).fetchall()
    tasks = []
    for row in rows:
        try:
            tasks.append(_decode(dict(row)))
        except Exception as exc:  # noqa: BLE001 — one corrupt row must not break the table
            logger.warning("schedule_store_row_decode_failed id=%s error=%s", row["id"], exc)
    return tasks


def get(task_id: str) -> dict[str, Any] | None:
    """Return a single task by id, or None."""
    row = (
        _database()
        .execute("SELECT * FROM scheduled_tasks WHERE id = :id", {"id": task_id})
        .fetchone()
    )
    return _decode(dict(row)) if row is not None else None


def set_enabled(task_id: str, enabled: bool) -> bool:
    """Toggle a task's enabled flag (pause/resume). Returns True if a row matched."""
    result = _database().execute(
        "UPDATE scheduled_tasks SET enabled = :enabled WHERE id = :id",
        {"enabled": 1 if enabled else 0, "id": task_id},
    )
    return result.rowcount > 0


_UNSET = object()


def update_run_state(
    task_id: str,
    *,
    last_run_at: str | None = _UNSET,  # type: ignore[assignment]
    last_status: str | None = _UNSET,  # type: ignore[assignment]
    last_error: str | None = _UNSET,  # type: ignore[assignment]
    next_run_at: str | None = _UNSET,  # type: ignore[assignment]
) -> None:
    """Write back observability/runtime-state columns after a fire (field-selective).

    Only columns the caller explicitly passes are updated (PATCH semantics) — an omitted
    keyword leaves that column untouched. This is load-bearing: the poll engine calls this
    from two independent call sites (post-fire run-state writeback, and next_run_at backfill
    at registration) that must never clobber each other's column (fix-cron-store-and-once
    F1 — a prior unconditional 4-column UPDATE wiped next_run_at on every fire, forcing a
    stale-grid recompute on the next tick and cumulative interval drift).
    """
    columns = {
        "last_run_at": last_run_at,
        "last_status": last_status,
        "last_error": last_error,
        "next_run_at": next_run_at,
    }
    provided = {k: v for k, v in columns.items() if v is not _UNSET}
    if not provided:
        return
    set_clause = ", ".join(f"{col} = :{col}" for col in provided)
    _database().execute(
        f"UPDATE scheduled_tasks SET {set_clause} WHERE id = :id",
        {"id": task_id, **provided},
    )


def claim_next_run(task_id: str, *, expected: str | None, new: str) -> bool:
    """Atomically advance ``next_run_at`` only if it still equals ``expected``.

    Used by the poll engine to claim a due recurring occurrence before executing it: the
    conditional update makes the claim idempotent, so overlapping ticks (or a concurrent
    ``run_now``) can never double-fire the same occurrence. Returns True iff this caller won
    the claim (exactly one row updated).
    """
    if expected is None:
        result = _database().execute(
            "UPDATE scheduled_tasks SET next_run_at = :new WHERE id = :id AND next_run_at IS NULL",
            {"id": task_id, "new": new},
        )
    else:
        result = _database().execute(
            "UPDATE scheduled_tasks SET next_run_at = :new "
            "WHERE id = :id AND next_run_at = :expected",
            {"id": task_id, "new": new, "expected": expected},
        )
    return result.rowcount == 1


def delete(task_id: str) -> bool:
    with _database().transaction() as conn:
        # Cascade run history so a deleted task leaves no orphaned rows.
        conn.execute(
            "DELETE FROM scheduled_task_runs WHERE task_id = :task_id", {"task_id": task_id}
        )
        result = conn.execute(
            "DELETE FROM scheduled_tasks WHERE id = :task_id", {"task_id": task_id}
        )
        return result.rowcount > 0


# Default per-task run-history rows retained; the engine passes an explicit value.
_DEFAULT_RUN_RETENTION = 50


def record_run(
    task_id: str,
    *,
    status: str,
    fired_at: str,
    kind: str | None = None,
    agent_error: str | None = None,
    delivery_error: str | None = None,
    duration_ms: int | None = None,
    retention: int = _DEFAULT_RUN_RETENTION,
) -> None:
    """Append one run-history row and prune to the newest ``retention`` rows for the task.

    ``status`` is one of ``ok`` / ``error`` / ``missed`` / ``skipped``. ``agent_error`` and
    ``delivery_error`` are tracked separately (a run can produce output yet fail delivery).
    """
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _database().transaction() as conn:
        conn.execute(
            "INSERT INTO scheduled_task_runs ("
            "task_id, fired_at, status, agent_error, delivery_error, duration_ms, kind, created_at"
            ") VALUES ("
            ":task_id, :fired_at, :status, :agent_error, :delivery_error, :duration_ms, :kind, "
            ":created_at)",
            {
                "task_id": task_id,
                "fired_at": fired_at,
                "status": status,
                "agent_error": agent_error,
                "delivery_error": delivery_error,
                "duration_ms": duration_ms,
                "kind": kind,
                "created_at": now,
            },
        )
        if retention > 0:
            conn.execute(
                "DELETE FROM scheduled_task_runs WHERE task_id = :task_id AND id NOT IN ("
                "SELECT id FROM scheduled_task_runs WHERE task_id = :task_id "
                "ORDER BY id DESC LIMIT :retention)",
                {"task_id": task_id, "retention": retention},
            )


def list_runs(task_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return the most recent runs for a task, newest first."""
    rows = (
        _database()
        .execute(
            "SELECT * FROM scheduled_task_runs WHERE task_id = :task_id "
            "ORDER BY id DESC LIMIT :limit",
            {"task_id": task_id, "limit": limit},
        )
        .fetchall()
    )
    return [dict(row) for row in rows]


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    """Deserialize JSON columns (origin/deliver) back into dicts for callers."""
    out = dict(row)
    for key in ("origin", "deliver"):
        val = out.get(key)
        if isinstance(val, str):
            out[key] = json.loads(val)
    return out
