"""Integration test: approvals.id column must accept UUID-string values.

The runtime generates approval IDs as str(uuid.uuid4())[:8] (text), but the
original migration created approvals.id as INTEGER. This test verifies the
migration fix (060) produces a TEXT-compatible column.
"""

from __future__ import annotations

import sqlite3

import pytest

from tests.integration.test_migrations import apply_migrations


@pytest.fixture()
def migrated_db(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    return db


def test_approvals_id_accepts_uuid_string(migrated_db):
    """approvals.id must accept a short UUID hex string, not just integers."""
    conn = sqlite3.connect(migrated_db)
    try:
        conn.execute(
            "INSERT INTO approvals "
            "(id, session_id, requester_user_id, risk_level, tool_name, tool_args, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("a1b2c3d4", "sess-1", "user-1", "medium", "run_code", "{}", "pending", "2024-01-01"),
        )
        conn.commit()
        rows = list(conn.execute("SELECT id FROM approvals WHERE id = 'a1b2c3d4'"))
        assert rows == [("a1b2c3d4",)], "UUID string id should be stored and retrievable"
    except Exception as exc:
        raise AssertionError(
            f"approvals.id rejected UUID string 'a1b2c3d4': {exc}. "
            "Migration 060 must change id from INTEGER to TEXT."
        ) from exc
    finally:
        conn.close()
