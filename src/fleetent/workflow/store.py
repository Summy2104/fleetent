"""SQLite persistence for workflow runs and step attempts.

Agent-owned store: schema is created by the unified agent_state.db embedded
migrations. Access the table through the DB injected via ``set_state_db(db)`` —
the same agent_state.db handle used by traces/approvals/schedule. No platform
imports. All SQL uses named parameters.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fleetent.db import SQLiteDatabase
from fleetent.structured_logging import get_logger
from fleetent.workflow.errors import WorkflowError

logger = get_logger("workflow_store")

_state_db: SQLiteDatabase | None = None

# Run/step terminal states — a transition FROM any of these is illegal (immutable).
RUN_TERMINAL = frozenset({"succeeded", "failed", "cancelled"})
STEP_TERMINAL = frozenset({"succeeded", "failed", "skipped", "cancelled"})

_DEFAULT_RUN_RETENTION = 50


def set_state_db(db: SQLiteDatabase) -> None:
    """Inject the per-agent state DB. Called once at agent boot via agent_app."""
    global _state_db
    _state_db = db


def _database() -> SQLiteDatabase:
    if _state_db is None:
        raise RuntimeError(
            "workflow_store: state_db not initialized — call set_state_db(db) at boot"
        )
    return _state_db


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── run lifecycle ─────────────────────────────────────────────────────────────


def create_run(
    *,
    run_id: str,
    workflow_name: str,
    definition: dict[str, Any],
    inputs: dict[str, Any] | None,
    principal: dict[str, Any] | None,
    origin: dict[str, Any] | None,
    deliver: dict[str, Any] | None,
    step_ids: list[str],
    now: str | None = None,
) -> None:
    """Insert a run (status ``pending``) plus one ``pending`` step_run per step.

    ``definition`` and ``principal`` are frozen as JSON so the run is reproducible
    regardless of later edits to the on-disk workflow.yaml.
    """
    ts = now or _now()
    run_row = {
        "id": run_id,
        "workflow_name": workflow_name,
        "definition_json": json.dumps(definition, ensure_ascii=False),
        "status": "pending",
        "inputs_json": json.dumps(inputs or {}, ensure_ascii=False),
        "principal_json": json.dumps(principal) if principal is not None else None,
        "origin_json": json.dumps(origin) if origin is not None else None,
        "deliver_json": json.dumps(deliver) if deliver is not None else None,
        "error": None,
        "created_at": ts,
        "started_at": None,
        "ended_at": None,
    }
    with _database().transaction() as conn:
        conn.execute(
            "INSERT INTO workflow_runs ("
            "id, workflow_name, definition_json, status, inputs_json, principal_json, "
            "origin_json, deliver_json, error, created_at, started_at, ended_at"
            ") VALUES ("
            ":id, :workflow_name, :definition_json, :status, :inputs_json, :principal_json, "
            ":origin_json, :deliver_json, :error, :created_at, :started_at, :ended_at)",
            run_row,
        )
        for step_id in step_ids:
            conn.execute(
                "INSERT INTO workflow_step_runs ("
                "run_id, step_id, attempt, status, output_json, error, claimed_at, "
                "started_at, ended_at) VALUES ("
                ":run_id, :step_id, 1, 'pending', NULL, NULL, NULL, NULL, NULL)",
                {"run_id": run_id, "step_id": step_id},
            )


def get_run(run_id: str) -> dict[str, Any] | None:
    row = (
        _database().execute("SELECT * FROM workflow_runs WHERE id = :id", {"id": run_id}).fetchone()
    )
    return _decode_run(dict(row)) if row is not None else None


def list_active_runs() -> list[dict[str, Any]]:
    """Non-terminal runs (pending/running), oldest first — the sweep/resume work set."""
    rows = (
        _database()
        .execute(
            "SELECT * FROM workflow_runs WHERE status NOT IN ('succeeded','failed','cancelled') "
            "ORDER BY created_at ASC, id ASC"
        )
        .fetchall()
    )
    return [_decode_run(dict(r)) for r in rows]


def list_runs(workflow_name: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    if workflow_name is not None:
        sql = (
            "SELECT * FROM workflow_runs WHERE workflow_name = :name "
            "ORDER BY created_at DESC, id DESC LIMIT :limit"
        )
        params: dict[str, Any] = {"name": workflow_name, "limit": limit}
    else:
        sql = "SELECT * FROM workflow_runs ORDER BY created_at DESC, id DESC LIMIT :limit"
        params = {"limit": limit}
    rows = _database().execute(sql, params).fetchall()
    return [_decode_run(dict(r)) for r in rows]


def set_run_status(
    run_id: str,
    status: str,
    *,
    error: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> None:
    """Update a run's status, rejecting a transition out of a terminal state."""
    current = get_run(run_id)
    if current is None:
        raise WorkflowError(f"unknown run {run_id!r}")
    if current["status"] in RUN_TERMINAL:
        raise WorkflowError(
            f"illegal run transition {current['status']!r} -> {status!r} (run is terminal)"
        )
    fields: dict[str, Any] = {"status": status}
    if error is not None:
        fields["error"] = error
    if started_at is not None:
        fields["started_at"] = started_at
    if ended_at is not None:
        fields["ended_at"] = ended_at
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    _database().execute(
        f"UPDATE workflow_runs SET {set_clause} WHERE id = :id",
        {"id": run_id, **fields},
    )


# ── step lifecycle ────────────────────────────────────────────────────────────


def get_step(run_id: str, step_id: str, attempt: int | None = None) -> dict[str, Any] | None:
    """Return a step attempt row; the latest attempt when ``attempt`` is None."""
    if attempt is not None:
        row = (
            _database()
            .execute(
                "SELECT * FROM workflow_step_runs "
                "WHERE run_id = :run_id AND step_id = :step_id AND attempt = :attempt",
                {"run_id": run_id, "step_id": step_id, "attempt": attempt},
            )
            .fetchone()
        )
    else:
        row = (
            _database()
            .execute(
                "SELECT * FROM workflow_step_runs "
                "WHERE run_id = :run_id AND step_id = :step_id "
                "ORDER BY attempt DESC LIMIT 1",
                {"run_id": run_id, "step_id": step_id},
            )
            .fetchone()
        )
    return _decode_step(dict(row)) if row is not None else None


def list_steps(run_id: str) -> list[dict[str, Any]]:
    """Latest attempt per step for a run."""
    rows = (
        _database()
        .execute(
            "SELECT * FROM workflow_step_runs w WHERE run_id = :run_id "
            "AND attempt = (SELECT MAX(attempt) FROM workflow_step_runs "
            "               WHERE run_id = w.run_id AND step_id = w.step_id) "
            "ORDER BY step_id",
            {"run_id": run_id},
        )
        .fetchall()
    )
    return [_decode_step(dict(r)) for r in rows]


def claim_step(run_id: str, step_id: str, attempt: int, *, now: str | None = None) -> bool:
    """Atomically transition a step attempt pending -> running (idempotent claim).

    Conditional UPDATE: only the row still in ``pending`` is claimed, so overlapping
    hot-path and sweep drivers can never double-run the same attempt. Returns True
    iff this caller won the claim (exactly one row updated).
    """
    ts = now or _now()
    result = _database().execute(
        "UPDATE workflow_step_runs SET status = 'running', claimed_at = :ts, started_at = :ts "
        "WHERE run_id = :run_id AND step_id = :step_id AND attempt = :attempt "
        "AND status = 'pending'",
        {"run_id": run_id, "step_id": step_id, "attempt": attempt, "ts": ts},
    )
    return result.rowcount == 1


def finish_step(
    run_id: str,
    step_id: str,
    attempt: int,
    *,
    status: str,
    output: Any | None = None,
    error: str | None = None,
    now: str | None = None,
) -> None:
    """Move a step attempt to a terminal status, rejecting a transition from terminal."""
    current = get_step(run_id, step_id, attempt)
    if current is None:
        raise WorkflowError(f"unknown step attempt {run_id}/{step_id}#{attempt}")
    if current["status"] in STEP_TERMINAL:
        raise WorkflowError(
            f"illegal step transition {current['status']!r} -> {status!r} "
            f"({run_id}/{step_id}#{attempt} is terminal)"
        )
    _database().execute(
        "UPDATE workflow_step_runs SET status = :status, output_json = :output_json, "
        "error = :error, ended_at = :ended_at "
        "WHERE run_id = :run_id AND step_id = :step_id AND attempt = :attempt",
        {
            "run_id": run_id,
            "step_id": step_id,
            "attempt": attempt,
            "status": status,
            "output_json": json.dumps(output, ensure_ascii=False) if output is not None else None,
            "error": error,
            "ended_at": now or _now(),
        },
    )


def skip_step(run_id: str, step_id: str, *, now: str | None = None) -> None:
    """Cascade-skip: mark the latest pending attempt of a step as skipped."""
    current = get_step(run_id, step_id)
    if current is None or current["status"] in STEP_TERMINAL:
        return  # already resolved; nothing to skip
    _database().execute(
        "UPDATE workflow_step_runs SET status = 'skipped', ended_at = :ended_at "
        "WHERE run_id = :run_id AND step_id = :step_id AND attempt = :attempt",
        {
            "run_id": run_id,
            "step_id": step_id,
            "attempt": current["attempt"],
            "ended_at": now or _now(),
        },
    )


def cancel_open_steps(run_id: str, *, now: str | None = None) -> None:
    """Mark every non-terminal step attempt of a run as cancelled (run cancellation)."""
    _database().execute(
        "UPDATE workflow_step_runs SET status = 'cancelled', ended_at = :ts "
        "WHERE run_id = :run_id AND status IN ('pending','running')",
        {"run_id": run_id, "ts": now or _now()},
    )


def reclaim_expired_step(
    run_id: str, step_id: str, attempt: int, *, now: str | None = None
) -> int | None:
    """Fail an expired running attempt and open a fresh ``attempt+1`` pending row.

    Returns the new attempt number, or None if the row was not in ``running``
    (someone else already resolved it). Used by sweep to recover a step whose
    ``claimed_at`` outlived its claim window (e.g. the process crashed mid-step).
    """
    ts = now or _now()
    result = _database().execute(
        "UPDATE workflow_step_runs SET status = 'failed', error = 'claim expired (reclaimed)', "
        "ended_at = :ts WHERE run_id = :run_id AND step_id = :step_id AND attempt = :attempt "
        "AND status = 'running'",
        {"run_id": run_id, "step_id": step_id, "attempt": attempt, "ts": ts},
    )
    if result.rowcount != 1:
        return None
    new_attempt = attempt + 1
    _database().execute(
        "INSERT INTO workflow_step_runs ("
        "run_id, step_id, attempt, status, output_json, error, claimed_at, started_at, ended_at"
        ") VALUES (:run_id, :step_id, :attempt, 'pending', NULL, NULL, NULL, NULL, NULL)",
        {"run_id": run_id, "step_id": step_id, "attempt": new_attempt},
    )
    return new_attempt


def open_retry_attempt(run_id: str, step_id: str, attempt: int) -> int:
    """Open a fresh ``attempt+1`` pending row for a step (retry after failure)."""
    new_attempt = attempt + 1
    _database().execute(
        "INSERT INTO workflow_step_runs ("
        "run_id, step_id, attempt, status, output_json, error, claimed_at, started_at, ended_at"
        ") VALUES (:run_id, :step_id, :attempt, 'pending', NULL, NULL, NULL, NULL, NULL)",
        {"run_id": run_id, "step_id": step_id, "attempt": new_attempt},
    )
    return new_attempt


# ── retention ─────────────────────────────────────────────────────────────────


def prune_runs(workflow_name: str, *, retention: int = _DEFAULT_RUN_RETENTION) -> None:
    """Delete terminal runs for a workflow beyond the newest ``retention`` (and their steps)."""
    if retention <= 0:
        return
    with _database().transaction() as conn:
        stale = conn.execute(
            "SELECT id FROM workflow_runs WHERE workflow_name = :name AND status IN "
            "('succeeded','failed','cancelled') ORDER BY created_at DESC, id DESC "
            "LIMIT -1 OFFSET :retention",
            {"name": workflow_name, "retention": retention},
        ).fetchall()
        for row in stale:
            rid = row["id"]
            conn.execute("DELETE FROM workflow_step_runs WHERE run_id = :id", {"id": rid})
            conn.execute("DELETE FROM workflow_runs WHERE id = :id", {"id": rid})


# ── decode ────────────────────────────────────────────────────────────────────


def _decode_run(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["definition"] = json.loads(out["definition_json"]) if out.get("definition_json") else None
    out["inputs"] = json.loads(out["inputs_json"]) if out.get("inputs_json") else {}
    out["principal"] = json.loads(out["principal_json"]) if out.get("principal_json") else None
    out["origin"] = json.loads(out["origin_json"]) if out.get("origin_json") else None
    out["deliver"] = json.loads(out["deliver_json"]) if out.get("deliver_json") else None
    return out


def _decode_step(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["output"] = json.loads(out["output_json"]) if out.get("output_json") else None
    return out
