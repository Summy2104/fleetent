"""Integration tests for the unified approval_request store."""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


@pytest.fixture()
def state_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


@pytest.fixture(autouse=True)
def _inject_db(state_db: SQLiteDatabase, monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.governance import approval_request_store

    monkeypatch.setattr(approval_request_store, "_state_db", state_db)


def test_create_update_and_fetch_approval_requests() -> None:
    from fleetent.governance import approval_request_store

    approval_request_store.create_request(
        id="tool-1",
        subject_type="tool_call",
        subject_id="tool-1",
        requester_user_id="alice",
        risk="high",
        routing_key="delete_db",
        created_at="2026-06-10T10:00:00+00:00",
    )
    approval_request_store.create_request(
        id="memory-1",
        subject_type="memory_proposal",
        subject_id="memory-1",
        requester_user_id=None,
        risk="medium",
        routing_key="reflection_memory_proposal",
        created_at="2026-06-10T10:01:00+00:00",
        expires_at="2026-06-11T10:01:00+00:00",
    )
    approval_request_store.create_request(
        id="skill-1",
        subject_type="skill_proposal",
        subject_id="skill-1",
        requester_user_id=None,
        risk="medium",
        routing_key="reflection_skill_proposal",
        created_at="2026-06-10T10:02:00+00:00",
    )

    approval_request_store.decide_request(
        id="tool-1",
        status="approved",
        decided_at="2026-06-10T10:03:00+00:00",
        approver_user_id="manager-1",
    )
    approval_request_store.decide_request(
        id="memory-1",
        status="rejected",
        decided_at="2026-06-10T10:04:00+00:00",
        approver_user_id="manager-2",
        reason="not safe",
    )
    approval_request_store.decide_request(
        id="skill-1",
        status="expired",
        decided_at="2026-06-10T10:05:00+00:00",
    )

    assert approval_request_store.get_request("tool-1") == {
        "id": "tool-1",
        "subject_type": "tool_call",
        "subject_id": "tool-1",
        "requester_user_id": "alice",
        "risk": "high",
        "status": "approved",
        "approver_user_id": "manager-1",
        "decided_at": "2026-06-10T10:03:00+00:00",
        "reason": None,
        "routing_key": "delete_db",
        "created_at": "2026-06-10T10:00:00+00:00",
        "expires_at": None,
    }
    assert approval_request_store.get_request("memory-1")["reason"] == "not safe"
    assert approval_request_store.get_request("skill-1")["status"] == "expired"


def test_list_pending_requests_across_subject_types() -> None:
    from fleetent.governance import approval_request_store

    approval_request_store.create_request(
        id="tool-1",
        subject_type="tool_call",
        subject_id="tool-1",
        requester_user_id="alice",
        risk="high",
        routing_key="delete_db",
        created_at="2026-06-10T10:00:00+00:00",
    )
    approval_request_store.create_request(
        id="memory-1",
        subject_type="memory_proposal",
        subject_id="memory-1",
        requester_user_id=None,
        risk="medium",
        routing_key="reflection_memory_proposal",
        created_at="2026-06-10T10:01:00+00:00",
    )
    approval_request_store.create_request(
        id="skill-1",
        subject_type="skill_proposal",
        subject_id="skill-1",
        requester_user_id=None,
        risk="low",
        routing_key="reflection_skill_proposal",
        created_at="2026-06-10T10:02:00+00:00",
    )
    approval_request_store.decide_request(
        id="skill-1",
        status="approved",
        decided_at="2026-06-10T10:03:00+00:00",
        approver_user_id="manager-1",
    )

    pending = approval_request_store.list_requests(status="pending")
    assert [row["id"] for row in pending] == ["memory-1", "tool-1"]

    tool_pending = approval_request_store.list_requests(
        status="pending",
        subject_type="tool_call",
    )
    assert [row["id"] for row in tool_pending] == ["tool-1"]

    memory_pending = approval_request_store.list_requests(
        status="pending",
        subject_type="memory_proposal",
    )
    assert [row["id"] for row in memory_pending] == ["memory-1"]
