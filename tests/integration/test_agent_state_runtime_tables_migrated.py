"""agent-runtime-db-routing-cleanup: the four agent-runtime tables join the
unified per-agent MIGRATIONS so they land in agent_state.db, not the management DB."""

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
    "memory_maintenance_proposals": {
        "id",
        "user_id",
        "action",
        "target_memory_ids_json",
        "proposed_content",
        "metadata_patch_json",
        "risk",
        "reason",
        "evidence_ids_json",
        "status",
        "created_at",
        "updated_at",
        "expires_at",
    },
    "skill_proposals": {
        "id",
        "type",
        "target_skill",
        "reason",
        "evidence_refs_json",
        "risk_level",
        "suggested_draft",
        "suggested_diff",
        "status",
        "reviewer_user_id",
        "reviewed_at",
        "rejection_reason",
        "actor_user_id",
        "applied_at",
        "created_at",
        "updated_at",
    },
}

_EXPECTED_INDEXES = {
    "idx_sub_agent_runs_parent",
    "idx_memory_maintenance_user_status",
    "idx_skill_proposals_status_updated",
}


def _open_migrated(tmp_path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, MIGRATIONS)
    return db


def test_unified_migrations_create_four_runtime_tables(tmp_path):
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
