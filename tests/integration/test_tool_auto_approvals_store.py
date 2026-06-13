"""Integration tests for the tool auto-approval store (approval-minimization).

Connection is injected via monkeypatch on _state_db (3b-4 set_state_db pattern).
Verifies grant/lookup/list and idempotent re-grant.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.governance import tool_auto_approvals_store as store
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


@pytest.fixture()
def state_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


@pytest.fixture(autouse=True)
def _inject_db(state_db: SQLiteDatabase, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "_state_db", state_db)


def test_grant_then_allowed() -> None:
    fp = store.fingerprint("user:alice", "run_code", {"code": "print(1)"})
    assert store.is_allowed(fp) is False
    store.add_grant(
        fingerprint=fp,
        scope_key="user:alice",
        tool_name="run_code",
        created_at="2026-06-09T00:00:00Z",
        created_by="slack:U_LEAD",
    )
    assert store.is_allowed(fp) is True


def test_unknown_fingerprint_not_allowed() -> None:
    assert store.is_allowed("deadbeef" * 8) is False


def test_list_grants_returns_rows() -> None:
    fp = store.fingerprint("u", "t", {"x": 1})
    store.add_grant(
        fingerprint=fp,
        scope_key="u",
        tool_name="t",
        created_at="2026-06-09T00:00:00Z",
    )
    grants = store.list_grants()
    assert len(grants) == 1
    assert grants[0]["fingerprint"] == fp
    assert grants[0]["tool_name"] == "t"


def test_re_grant_is_idempotent() -> None:
    fp = store.fingerprint("u", "t", {"x": 1})
    for _ in range(3):
        store.add_grant(
            fingerprint=fp,
            scope_key="u",
            tool_name="t",
            created_at="2026-06-09T00:00:00Z",
        )
    assert len(store.list_grants()) == 1
