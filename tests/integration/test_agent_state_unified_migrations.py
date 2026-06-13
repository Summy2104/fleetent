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


def _fetch_all(db_path: Path, sql: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql).fetchall()
    conn.close()
    return rows


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
    assert cols == {
        "session_id",
        "user_id",
        "created_at",
        "updated_at",
        "message_count",
    }


def test_migrate_drops_agent_name_from_legacy_sessions_table(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    conn = sqlite3.connect(db.path)
    conn.execute(
        """
        CREATE TABLE sessions (
            session_id    TEXT PRIMARY KEY,
            user_id       TEXT,
            created_at    REAL,
            updated_at    REAL,
            message_count INTEGER,
            agent_name    TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO sessions (
            session_id, user_id, created_at, updated_at, message_count, agent_name
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("sess-1", "u1", 1.0, 2.0, 3, "bot"),
    )
    # A faithful post-v27 DB also has scheduled_tasks (created at v27); later ALTERs
    # (v29/v30 add task_type/notify_text) require it to exist.
    conn.execute(
        "CREATE TABLE scheduled_tasks (id TEXT PRIMARY KEY, schedule_kind TEXT, enabled INTEGER)"
    )
    # approvals was created at v12; v31 renames approver_actor → approver_user_id so it
    # must be present in any faithful post-v12 legacy DB.
    conn.execute(
        "CREATE TABLE approvals ("
        "id TEXT PRIMARY KEY, session_id TEXT NOT NULL, requester_user_id TEXT NOT NULL, "
        "risk_level TEXT NOT NULL, tool_name TEXT NOT NULL, tool_args TEXT NOT NULL, "
        "status TEXT NOT NULL, approver_actor TEXT, created_at TEXT NOT NULL, resolved_at TEXT)"
    )
    # reflection_proposals was created at v24, so any faithful post-v27 DB must carry the
    # pre-report_id schema before v32 appends the nullable provenance column.
    conn.execute(
        """
        CREATE TABLE reflection_proposals (
          id                TEXT PRIMARY KEY,
          domain            TEXT NOT NULL,
          kind              TEXT NOT NULL,
          subject_user_id   TEXT,
          target_ref        TEXT,
          payload_json      TEXT NOT NULL,
          reason            TEXT NOT NULL,
          evidence_json     TEXT NOT NULL,
          risk              TEXT NOT NULL,
          status            TEXT NOT NULL,
          reviewer_user_id  TEXT,
          reviewed_at       TEXT,
          rejection_reason  TEXT,
          actor_user_id     TEXT,
          applied_at        TEXT,
          expires_at        TEXT,
          created_at        TEXT NOT NULL,
          updated_at        TEXT NOT NULL
        )
        """
    )
    conn.execute("PRAGMA user_version = 27")
    conn.commit()
    conn.close()

    migrate(db, AGENT_STATE_MIGRATIONS)

    assert "agent_name" not in _columns(db.path, "sessions")
    conn = sqlite3.connect(db.path)
    row = conn.execute(
        "SELECT session_id, user_id, created_at, updated_at, message_count FROM sessions"
    ).fetchone()
    conn.close()
    assert row == ("sess-1", "u1", 1.0, 2.0, 3)


def test_traces_columns_match_ensure_schema(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    cols = _columns(db.path, "traces")
    assert cols == {
        "id",
        "run_id",
        "span_id",
        "parent_span_id",
        "session_id",
        "user_id",
        "agent_id",
        "tenant_id",
        "event_type",
        "ts",
        "payload_json",
    }


def test_reflection_reports_columns_match_ensure_schema(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    cols = _columns(db.path, "reflection_reports")
    assert cols == {
        "id",
        "scope",
        "domain",
        "time_window_start",
        "time_window_end",
        "findings_json",
        "signal_summary_json",
        "created_at",
    }


def test_migrate_v33_approval_data_into_unified_approval_requests(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    conn = sqlite3.connect(db.path)
    conn.execute(
        """
        CREATE TABLE approvals (
            id                TEXT PRIMARY KEY,
            session_id        TEXT NOT NULL,
            requester_user_id TEXT NOT NULL,
            risk_level        TEXT NOT NULL,
            tool_name         TEXT NOT NULL,
            tool_args         TEXT NOT NULL,
            status            TEXT NOT NULL,
            approver_user_id  TEXT,
            created_at        TEXT NOT NULL,
            resolved_at       TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO approvals (
            id, session_id, requester_user_id, risk_level, tool_name, tool_args,
            status, approver_user_id, created_at, resolved_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "apr_tool",
            "sess-1",
            "alice",
            "high",
            "delete_db",
            '{"table":"users"}',
            "approved",
            "manager-1",
            "2026-06-10T10:00:00+00:00",
            "2026-06-10T10:05:00+00:00",
        ),
    )
    conn.execute(
        """
        CREATE TABLE approval_allowlist (
            fingerprint TEXT PRIMARY KEY,
            scope_key   TEXT NOT NULL,
            tool_name   TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            created_by  TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO approval_allowlist (fingerprint, scope_key, tool_name, created_at, created_by)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("fp-1", "default", "delete_db", "2026-06-10T10:00:00+00:00", "manager-1"),
    )
    conn.execute(
        """
        CREATE TABLE reflection_proposals (
          id                TEXT PRIMARY KEY,
          domain            TEXT NOT NULL,
          kind              TEXT NOT NULL,
          subject_user_id   TEXT,
          target_ref        TEXT,
          payload_json      TEXT NOT NULL,
          reason            TEXT NOT NULL,
          evidence_json     TEXT NOT NULL,
          risk              TEXT NOT NULL,
          status            TEXT NOT NULL,
          reviewer_user_id  TEXT,
          reviewed_at       TEXT,
          rejection_reason  TEXT,
          actor_user_id     TEXT,
          applied_at        TEXT,
          expires_at        TEXT,
          created_at        TEXT NOT NULL,
          updated_at        TEXT NOT NULL,
          report_id         TEXT
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO reflection_proposals (
          id, domain, kind, subject_user_id, target_ref, payload_json, reason,
          evidence_json, risk, status, reviewer_user_id, reviewed_at, rejection_reason,
          actor_user_id, applied_at, expires_at, created_at, updated_at, report_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "mem-1",
                "memory",
                "promote_fact",
                "alice",
                "memory:1",
                '{"memory":"x"}',
                "keep it",
                "[]",
                "medium",
                "pending",
                None,
                None,
                None,
                None,
                None,
                "2026-06-11T00:00:00+00:00",
                "2026-06-10T09:00:00+00:00",
                "2026-06-10T09:00:00+00:00",
                "report-1",
            ),
            (
                "skill-1",
                "skill",
                "update_skill",
                "alice",
                "skill:1",
                '{"skill":"y"}',
                "improve it",
                "[]",
                "high",
                "rejected",
                "manager-2",
                "2026-06-11T01:00:00+00:00",
                "unsafe",
                None,
                None,
                "2026-06-12T00:00:00+00:00",
                "2026-06-10T09:30:00+00:00",
                "2026-06-10T09:30:00+00:00",
                "report-2",
            ),
        ],
    )
    conn.execute("PRAGMA user_version = 33")
    conn.commit()
    conn.close()

    migrate(db, AGENT_STATE_MIGRATIONS)

    tables = _tables(db.path)
    assert "approval_requests" in tables
    assert "approvals" not in tables
    assert "tool_auto_approvals" in tables
    assert "approval_allowlist" not in tables

    approval_rows = _fetch_all(
        db.path,
        """
        SELECT id, subject_type, subject_id, requester_user_id, risk, status,
               approver_user_id, decided_at, reason, routing_key, created_at, expires_at
        FROM approval_requests
        ORDER BY id
        """,
    )
    assert [dict(row) for row in approval_rows] == [
        {
            "id": "apr_tool",
            "subject_type": "tool_call",
            "subject_id": "sess-1",
            "requester_user_id": "alice",
            "risk": "high",
            "status": "approved",
            "approver_user_id": "manager-1",
            "decided_at": "2026-06-10T10:05:00+00:00",
            "reason": None,
            "routing_key": "delete_db",
            "created_at": "2026-06-10T10:00:00+00:00",
            "expires_at": None,
        },
        {
            "id": "mem-1",
            "subject_type": "memory_proposal",
            "subject_id": "mem-1",
            "requester_user_id": None,
            "risk": "medium",
            "status": "pending",
            "approver_user_id": None,
            "decided_at": None,
            "reason": None,
            "routing_key": "reflection_memory_proposal",
            "created_at": "2026-06-10T09:00:00+00:00",
            "expires_at": "2026-06-11T00:00:00+00:00",
        },
        {
            "id": "skill-1",
            "subject_type": "skill_proposal",
            "subject_id": "skill-1",
            "requester_user_id": None,
            "risk": "high",
            "status": "rejected",
            "approver_user_id": "manager-2",
            "decided_at": "2026-06-11T01:00:00+00:00",
            "reason": "unsafe",
            "routing_key": "reflection_skill_proposal",
            "created_at": "2026-06-10T09:30:00+00:00",
            "expires_at": "2026-06-12T00:00:00+00:00",
        },
    ]

    proposal_columns = _columns(db.path, "reflection_proposals")
    assert "status" not in proposal_columns
    assert "reviewer_user_id" not in proposal_columns
    assert "reviewed_at" not in proposal_columns
    assert "rejection_reason" not in proposal_columns
    assert "expires_at" not in proposal_columns

    renamed_rows = _fetch_all(
        db.path,
        """
        SELECT fingerprint, scope_key, tool_name, created_at, created_by
        FROM tool_auto_approvals
        """,
    )
    assert [dict(row) for row in renamed_rows] == [
        {
            "fingerprint": "fp-1",
            "scope_key": "default",
            "tool_name": "delete_db",
            "created_at": "2026-06-10T10:00:00+00:00",
            "created_by": "manager-1",
        }
    ]


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
    vector_backend = SQLiteVectorBackend(database_url=f"sqlite:///{agent_dir / 'agent_vectors.db'}")
    scope = AgentScope(state_db=state_db, vector_backend=vector_backend)

    db1 = scope.open_state_db(AGENT_STATE_MIGRATIONS)
    # Second open on an already-migrated DB must not raise SchemaTooNewError.
    db2 = scope.open_state_db(AGENT_STATE_MIGRATIONS)
    assert db1.path == db2.path


# ── 6: memory_items created (3b-3) ───────────────────────────────────────────


def test_unified_migrations_creates_memory_items_table(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    assert "memory_items" in _tables(db.path)


def test_memory_items_columns_no_namespace(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    cols = _columns(db.path, "memory_items")
    assert cols == {"id", "user_id", "type", "content", "created_at", "updated_at", "expires_at"}
    assert "namespace" not in cols


def test_memory_items_indexes_created(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    conn = __import__("sqlite3").connect(db.path)
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(memory_items)").fetchall()}
    conn.close()
    assert "idx_memory_items_user_type" in indexes
    assert "idx_memory_items_user_expires" in indexes


# ── 7: scheduled_tasks created (retire-standalone-fleetent-db) ───────────────


def test_unified_migrations_creates_scheduled_tasks_table(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    assert "scheduled_tasks" in _tables(db.path)


def test_scheduled_tasks_columns_complete(tmp_path: Path) -> None:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    cols = _columns(db.path, "scheduled_tasks")
    assert cols == {
        "id",
        "name",
        "task_type",
        "notify_text",
        "schedule_kind",
        "cron_expr",
        "run_at",
        "interval_seconds",
        "anchor",
        "timezone",
        "user_id",
        "message",
        "session_id",
        "origin",
        "deliver",
        "enabled",
        "source",
        "created_at",
        "last_run_at",
        "last_status",
        "last_error",
        "next_run_at",
    }
    assert "agent_name" not in cols


def test_fully_migrated_db_raises_schema_too_new_if_given_stale_list(
    tmp_path: Path,
) -> None:
    """Regression: a DB at current max must raise SchemaTooNewError when given
    a truncated list (only knows v1) — proving the unified list is required."""
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    # Minimal 1-step list — simulates what session/migrations.py used to be.
    stale_one_step: list[tuple[int, str]] = [(1, "SELECT 1")]

    db = _open(tmp_path)
    migrate(db, AGENT_STATE_MIGRATIONS)  # DB now at current max

    with pytest.raises(SchemaTooNewError):
        migrate(db, stale_one_step)  # only knows v1 — must refuse to open
