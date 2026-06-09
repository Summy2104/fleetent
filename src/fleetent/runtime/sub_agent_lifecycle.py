"""Sub-agent lifecycle: state machine + sqlite3 persistence + timeout (AR20).

A sub-agent task moves through a single-direction state machine
(`pending → running → {succeeded,failed,timed_out,cancelled}`, plus
`pending → cancelled`) and is recorded in the `sub_agent_runs` table of the
per-agent `fleetent.db`, queryable by `parent_session_id` for observability. This
module owns the lifecycle record and persistence; `sub_agent.py` keeps the
parallel orchestration. Standard-library `sqlite3` only (no ORM).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from enum import StrEnum

from fleetent.structured_logging import get_logger
from fleetent.user_store import DB_PATH as DB_PATH  # noqa: F401 — re-export for monkeypatch

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


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """Create the `sub_agent_runs` table and parent index, idempotently."""
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sub_agent_runs (
              run_id            TEXT PRIMARY KEY,
              parent_session_id TEXT NOT NULL,
              name              TEXT NOT NULL,
              state             TEXT NOT NULL,
              timeout_seconds   INTEGER NOT NULL,
              created_at        TEXT NOT NULL,
              started_at        TEXT,
              ended_at          TEXT,
              error             TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sub_agent_runs_parent "
            "ON sub_agent_runs(parent_session_id)"
        )


def upsert(lc: SubAgentLifecycle) -> None:
    """Insert or replace the lifecycle row keyed by run_id."""
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO sub_agent_runs
              (run_id, parent_session_id, name, state, timeout_seconds,
               created_at, started_at, ended_at, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
              state=excluded.state, started_at=excluded.started_at,
              ended_at=excluded.ended_at, error=excluded.error
            """,
            (
                lc.run_id,
                lc.parent_session_id,
                lc.name,
                lc.state.value,
                lc.timeout_seconds,
                lc.created_at,
                lc.started_at,
                lc.ended_at,
                lc.error,
            ),
        )


def query_by_parent(parent_session_id: str) -> list[SubAgentLifecycle]:
    """Return all sub-agent runs for a parent session with their latest state."""
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT run_id, parent_session_id, name, state, timeout_seconds,
                   created_at, started_at, ended_at, error
            FROM sub_agent_runs WHERE parent_session_id = ?
            ORDER BY created_at, run_id
            """,
            (parent_session_id,),
        ).fetchall()
    return [
        SubAgentLifecycle(
            run_id=r[0],
            parent_session_id=r[1],
            name=r[2],
            state=SubAgentState(r[3]),
            timeout_seconds=r[4],
            created_at=r[5],
            started_at=r[6],
            ended_at=r[7],
            error=r[8],
        )
        for r in rows
    ]
