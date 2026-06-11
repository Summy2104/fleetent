"""Sub-agent lifecycle: state machine + persistence + timeout (AR20).

A sub-agent task moves through a single-direction state machine
(`pending → running → {succeeded,failed,timed_out,cancelled}`, plus
`pending → cancelled`) and is recorded in the `sub_agent_runs` table of the
per-agent `agent_state.db`, queryable by `parent_session_id` for observability.
This module owns the lifecycle record and persistence; `sub_agent.py` keeps the
parallel orchestration. Reads/writes go through the unified `db.py` boundary on
the per-agent state DB injected at boot (no raw connection, no ORM).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from fleetent.db import SQLiteDatabase
from fleetent.structured_logging import get_logger

_logger = get_logger("runtime.sub_agent")

# Default per sub-agent wall-clock timeout; mirrors GovernanceConfig.sub_agent_timeout_seconds.
SUB_AGENT_TIMEOUT_SECONDS = 300


class SubAgentState(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    timed_out = "timed_out"
    cancelled = "cancelled"


# Single-direction legal transitions; terminal states never transition again.
_LEGAL_TRANSITIONS: dict[SubAgentState, frozenset[SubAgentState]] = {
    SubAgentState.pending: frozenset({SubAgentState.running, SubAgentState.cancelled}),
    SubAgentState.running: frozenset(
        {
            SubAgentState.succeeded,
            SubAgentState.failed,
            SubAgentState.timed_out,
            SubAgentState.cancelled,
        }
    ),
}


@dataclass
class SubAgentLifecycle:
    """One row of `sub_agent_runs`. Elapsed is derived (ended_at - started_at)."""

    run_id: str
    parent_session_id: str
    name: str
    timeout_seconds: int
    created_at: str
    state: SubAgentState = field(default=SubAgentState.pending)
    started_at: str | None = None
    ended_at: str | None = None
    error: str | None = None


def validate_transition(src: SubAgentState, dst: SubAgentState) -> None:
    """Raise ValueError on an illegal state transition (never swallow silently)."""
    if dst not in _LEGAL_TRANSITIONS.get(src, frozenset()):
        _logger.warn("sub_agent_illegal_transition", src=src, dst=dst)
        raise ValueError(f"illegal sub-agent state transition: {src} -> {dst}")


def resolve_timeout(timeout_seconds: int | None = None, config: int | None = None) -> int:
    """Resolve effective timeout. Precedence: call param > config > module default."""
    if timeout_seconds is not None:
        return timeout_seconds
    if config is not None:
        return config
    return SUB_AGENT_TIMEOUT_SECONDS


# Per-agent state DB, injected once at boot via agent_app._init_agent_db_schema.
# The sub_agent_runs table + index are created by the unified AGENT_STATE_MIGRATIONS,
# so this module never owns DDL or a raw connection — keeping sub-agent run records
# physically scoped to the running agent's agent_state.db, not a shared management DB.
_state_db: SQLiteDatabase | None = None


def set_state_db(db: SQLiteDatabase) -> None:
    """Inject the per-agent state DB.  Called once at agent boot."""
    global _state_db
    _state_db = db


def _db() -> SQLiteDatabase:
    if _state_db is None:
        raise RuntimeError(
            "runtime/sub_agent_lifecycle: state_db not initialized — call set_state_db(db) at boot"
        )
    return _state_db


def upsert(lc: SubAgentLifecycle) -> None:
    """Insert or replace the lifecycle row keyed by run_id."""
    _db().execute(
        """
        INSERT INTO sub_agent_runs
          (run_id, parent_session_id, name, state, timeout_seconds,
           created_at, started_at, ended_at, error)
        VALUES (:run_id, :parent_session_id, :name, :state, :timeout_seconds,
                :created_at, :started_at, :ended_at, :error)
        ON CONFLICT(run_id) DO UPDATE SET
          state=excluded.state, started_at=excluded.started_at,
          ended_at=excluded.ended_at, error=excluded.error
        """,
        {
            "run_id": lc.run_id,
            "parent_session_id": lc.parent_session_id,
            "name": lc.name,
            "state": lc.state.value,
            "timeout_seconds": lc.timeout_seconds,
            "created_at": lc.created_at,
            "started_at": lc.started_at,
            "ended_at": lc.ended_at,
            "error": lc.error,
        },
    )


def query_by_parent(parent_session_id: str) -> list[SubAgentLifecycle]:
    """Return all sub-agent runs for a parent session with their latest state."""
    rows = (
        _db()
        .execute(
            """
            SELECT run_id, parent_session_id, name, state, timeout_seconds,
                   created_at, started_at, ended_at, error
            FROM sub_agent_runs WHERE parent_session_id = :parent_session_id
            ORDER BY created_at, run_id
            """,
            {"parent_session_id": parent_session_id},
        )
        .fetchall()
    )
    return [
        SubAgentLifecycle(
            run_id=r["run_id"],
            parent_session_id=r["parent_session_id"],
            name=r["name"],
            state=SubAgentState(r["state"]),
            timeout_seconds=r["timeout_seconds"],
            created_at=r["created_at"],
            started_at=r["started_at"],
            ended_at=r["ended_at"],
            error=r["error"],
        )
        for r in rows
    ]
