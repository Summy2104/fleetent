"""Integration tests: approvals schema migrates into per-agent agent_state.db (3b-4).

Verifies that after Y migration the agent_state.db contains `approvals` and
`approval_allowlist` tables with correct columns, and that opening the same DB
twice is idempotent (no SchemaTooNewError).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _open_state_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


def test_approvals_table_exists_after_migration(tmp_path: Path) -> None:
    db = _open_state_db(tmp_path)
    tables = {
        r["name"]
        for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "approvals" in tables, "approvals table must be created by agent_state MIGRATIONS"


def test_approval_allowlist_table_exists_after_migration(tmp_path: Path) -> None:
    db = _open_state_db(tmp_path)
    tables = {
        r["name"]
        for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "approval_allowlist" in tables, (
        "approval_allowlist table must be created by agent_state MIGRATIONS"
    )


def test_approvals_columns_match_store_schema(tmp_path: Path) -> None:
    db = _open_state_db(tmp_path)
    cols = {r["name"] for r in db.execute("PRAGMA table_info(approvals)").fetchall()}
    required = {
        "id",
        "session_id",
        "requester_user_id",
        "risk_level",
        "tool_name",
        "tool_args",
        "status",
        "approver_user_id",
        "created_at",
        "resolved_at",
    }
    assert required.issubset(cols), f"approvals missing columns: {required - cols}"


def test_approval_allowlist_columns_match_store_schema(tmp_path: Path) -> None:
    db = _open_state_db(tmp_path)
    cols = {r["name"] for r in db.execute("PRAGMA table_info(approval_allowlist)").fetchall()}
    required = {"fingerprint", "scope_key", "tool_name", "created_at", "created_by"}
    assert required.issubset(cols), f"approval_allowlist missing columns: {required - cols}"


def test_consecutive_open_state_db_is_idempotent(tmp_path: Path) -> None:
    """Opening agent_state.db twice must not raise SchemaTooNewError."""
    db_path = tmp_path / "agent_state.db"
    migrate(SQLiteDatabase(path=db_path), AGENT_STATE_MIGRATIONS)
    migrate(SQLiteDatabase(path=db_path), AGENT_STATE_MIGRATIONS)  # must not raise


def test_approvals_column_is_approver_user_id(tmp_path: Path) -> None:
    """After latest Y migration approvals must have approver_user_id, not approver_actor."""
    db = _open_state_db(tmp_path)
    cols = {r["name"] for r in db.execute("PRAGMA table_info(approvals)").fetchall()}
    assert "approver_user_id" in cols, "approvals must have approver_user_id column"
    assert "approver_actor" not in cols, "approver_actor must be gone after rename migration"


def test_approvals_v31_rename_preserves_data(tmp_path: Path) -> None:
    """v31 renames approver_actor → approver_user_id; history values are preserved."""
    db_path = tmp_path / "agent_state.db"

    # Build pre-rename state: apply all migrations strictly before v31.
    pre_v31 = [m for m in AGENT_STATE_MIGRATIONS if m[0] < 31]
    migrate(SQLiteDatabase(path=db_path), pre_v31)

    # Directly insert a row with the old column name (bypassing the store layer).
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO approvals "
        "(id, session_id, requester_user_id, risk_level, tool_name, tool_args, "
        "status, created_at, approver_actor) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "upg-1",
            "s1",
            "u1",
            "medium",
            "tool_x",
            "{}",
            "approved",
            "2026-01-01T00:00:00+00:00",
            "slack:U_LEAD",
        ),
    )
    conn.commit()
    conn.close()

    # Apply full migrations including v31.
    migrate(SQLiteDatabase(path=db_path), AGENT_STATE_MIGRATIONS)

    # Column must be renamed.
    db2 = SQLiteDatabase(path=db_path)
    cols = {r["name"] for r in db2.execute("PRAGMA table_info(approvals)").fetchall()}
    assert "approver_user_id" in cols, "v31 must rename column to approver_user_id"
    assert "approver_actor" not in cols, "approver_actor must not exist after v31"

    # Historical value must be preserved under new column name.
    row = db2.execute("SELECT approver_user_id FROM approvals WHERE id = 'upg-1'").fetchone()
    assert row is not None
    assert row["approver_user_id"] == "slack:U_LEAD"
