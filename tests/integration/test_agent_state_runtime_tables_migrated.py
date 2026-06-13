"""Self-evolution tables are unified in agent_state.db via the embedded Y migrations."""

import sqlite3

from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS
from fleetent.schema_migrations import migrate

# Column sets lifted verbatim from the original DDL (context.py / sub_agent_lifecycle.py
# CREATE TABLE strings, and Alembic migrations 010 / 028). Asserting the full set guards
# against drift introduced while lifting.
_EXPECTED_COLUMNS = {
    "session_anti_flap": {
        "session_id",
        "recent_savings",
        "turns_since",
        "auto_disabled",
    },
    "sub_agent_runs": {
        "run_id",
        "parent_session_id",
        "name",
        "state",
        "timeout_seconds",
        "created_at",
        "started_at",
        "ended_at",
        "error",
    },
    "reflection_reports": {
        "id",
        "domain",
        "scope",
        "time_window_start",
        "time_window_end",
        "findings_json",
        "signal_summary_json",
        "created_at",
    },
    "reflection_proposals": {
        "id",
        "domain",
        "kind",
        "report_id",
        "subject_user_id",
        "target_ref",
        "payload_json",
        "reason",
        "evidence_json",
        "risk",
        "status",
        "reviewer_user_id",
        "reviewed_at",
        "rejection_reason",
        "actor_user_id",
        "applied_at",
        "expires_at",
        "created_at",
        "updated_at",
    },
}

_EXPECTED_INDEXES = {
    "idx_sub_agent_runs_parent",
    "idx_reflection_reports_scope_created",
}


def _open_migrated(tmp_path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, MIGRATIONS)
    return db


def test_unified_migrations_create_unified_runtime_tables(tmp_path):
    db = _open_migrated(tmp_path)
    conn = sqlite3.connect(db.path)
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table, expected in _EXPECTED_COLUMNS.items():
            assert table in tables, f"{table} missing from agent_state.db"
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert cols == expected, f"{table} column drift: {cols} != {expected}"

        indexes = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
        assert indexes >= _EXPECTED_INDEXES
        assert "memory_maintenance_proposals" not in tables
        assert "skill_proposals" not in tables
    finally:
        conn.close()


def test_unified_migrations_are_contiguous_and_idempotent(tmp_path):
    # Versions must remain contiguous from 1 (the embedded Y engine requires it),
    # and a second migrate() on an already-current DB must be a no-op.
    versions = [version for version, _ in MIGRATIONS]
    assert versions == list(range(1, len(MIGRATIONS) + 1))

    db = _open_migrated(tmp_path)
    migrate(db, MIGRATIONS)  # idempotent second pass
    conn = sqlite3.connect(db.path)
    try:
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()
    assert user_version == MIGRATIONS[-1][0]


def test_reflection_proposals_report_id_migrates_existing_rows_to_null(tmp_path):
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    report_id_version = next(
        version for version, sql in MIGRATIONS if "ADD COLUMN report_id TEXT" in sql
    )
    legacy_version = report_id_version - 1
    conn = sqlite3.connect(db.path)
    try:
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
        conn.execute(
            """
            INSERT INTO reflection_proposals (
                id, domain, kind, subject_user_id, target_ref, payload_json, reason,
                evidence_json, risk, status, reviewer_user_id, reviewed_at,
                rejection_reason, actor_user_id, applied_at, expires_at, created_at, updated_at
            )
            VALUES (
                'proposal-1', 'memory', 'rewrite', 'user-1', NULL, '{}', 'because',
                '[]', 'low', 'pending', NULL, NULL, NULL, NULL, NULL, NULL,
                '2026-06-13T00:00:00+00:00', '2026-06-13T00:00:00+00:00'
            )
            """
        )
        conn.execute(f"PRAGMA user_version = {legacy_version}")
        conn.commit()
    finally:
        conn.close()

    migrate(db, MIGRATIONS)

    conn = sqlite3.connect(db.path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(reflection_proposals)")}
        report_id = conn.execute(
            "SELECT report_id FROM reflection_proposals WHERE id = 'proposal-1'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert "report_id" in columns
    assert report_id is None
