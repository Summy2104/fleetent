"""Integration tests: unified per-agent MIGRATIONS (3b-2).

Verifies:
1. Empty agent_state.db after unified MIGRATIONS contains sessions(v1) + traces(v2-v6) +
   reflection_reports(v7-v8), DDL-equivalent to each store's ensure_schema output.
2. Regression guard: consecutive open_state_db calls (including on an already-migrated DB)
   do not raise SchemaTooNewError and do not rebuild existing tables.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.schema_migrations import SchemaTooNewError, migrate


def _open(tmp_path: Path, name: str = "agent_state.db") -> SQLiteDatabase:
    return SQLiteDatabase(path=tmp_path / name)


def _user_version(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    v = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    return v


def _columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    conn.close()
    return cols


def _tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    return names


# ── 1: AGENT_STATE_MIGRATIONS exists and is correctly ordered ─────────────────


def test_agent_state_migrations_is_importable() -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    assert len(AGENT_STATE_MIGRATIONS) >= 8, "Expected at least 8 steps (v1-v8)"
    versions = [v for v, _ in AGENT_STATE_MIGRATIONS]
    assert versions == list(range(1, len(AGENT_STATE_MIGRATIONS) + 1)), (
        "MIGRATIONS versions must be contiguous starting at 1"
    )


# ── 2: all three tables created in one migrate call ───────────────────────────


def test_unified_migrations_creates_sessions_table(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    assert "sessions" in _tables(db.path)


def test_unified_migrations_creates_traces_table(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    assert "traces" in _tables(db.path)


def test_unified_migrations_creates_reflection_reports_table(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    assert "reflection_reports" in _tables(db.path)


# ── 3: DDL equivalence with each store's ensure_schema output ─────────────────


def test_sessions_columns_match_ensure_schema(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    cols = _columns(db.path, "sessions")
    assert cols == {"session_id", "user_id", "created_at", "updated_at", "message_count", "agent_name"}


def test_traces_columns_match_ensure_schema(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    cols = _columns(db.path, "traces")
    assert cols == {
        "id", "run_id", "span_id", "parent_span_id", "session_id",
        "user_id", "agent_id", "tenant_id", "event_type", "ts", "payload_json",
    }


def test_reflection_reports_columns_match_ensure_schema(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    cols = _columns(db.path, "reflection_reports")
    assert cols == {
        "id", "scope", "time_window_start", "time_window_end", "findings_json", "created_at",
    }


# ── 4: user_version stamped at the highest step ───────────────────────────────


def test_user_version_stamped_at_highest_step(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    expected = max(v for v, _ in AGENT_STATE_MIGRATIONS)
    assert _user_version(db.path) == expected


# ── 5: regression guard — consecutive open_state_db never raises ──────────────


def test_consecutive_migrate_does_not_raise_schema_too_new(tmp_path: Path) -> None:
    """Two sequential migrate() calls on the same DB must not raise SchemaTooNewError."""
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    # Second call: DB is already at current_code_version — must be a no-op, not an error.
    migrate(db, AGENT_STATE_MIGRATIONS)
    assert _user_version(db.path) == max(v for v, _ in AGENT_STATE_MIGRATIONS)


def test_open_state_db_idempotent_via_agent_scope(tmp_path: Path) -> None:
    """AgentScope.open_state_db with AGENT_STATE_MIGRATIONS is safe to call twice."""
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
    from fleetent.tenant_router import AgentScope, SQLiteVectorBackend

    agent_dir = tmp_path / "default" / "test-agent"
    agent_dir.mkdir(parents=True)
    state_db = SQLiteDatabase(path=agent_dir / "agent_state.db")
    vector_backend = SQLiteVectorBackend(
        database_url=f"sqlite:///{agent_dir / 'agent_vectors.db'}"
    )
    scope = AgentScope(state_db=state_db, vector_backend=vector_backend)

    db1 = scope.open_state_db(AGENT_STATE_MIGRATIONS)
    # Second open on an already-migrated DB must not raise SchemaTooNewError.
    db2 = scope.open_state_db(AGENT_STATE_MIGRATIONS)
    assert db1.path == db2.path


def test_session_only_db_raises_schema_too_new_if_given_session_list_only(
    tmp_path: Path,
) -> None:
    """Regression: a DB already at v8 (unified) must raise SchemaTooNewError when given
    the old SESSION_MIGRATIONS list (only knows v1) — proving the unified list is required."""
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
    from fleetent.session.migrations import MIGRATIONS as SESSION_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)  # now at v8

    with pytest.raises(SchemaTooNewError):
        migrate(db, SESSION_MIGRATIONS)  # only knows v1 — must refuse to open
