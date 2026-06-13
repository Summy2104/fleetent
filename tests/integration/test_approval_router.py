from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

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


async def test_router_dispatches_by_subject_type_and_routes_reject_without_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleetent.governance import approval_request_store, approval_router

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
        risk="medium",
        routing_key="reflection_skill_proposal",
        created_at="2026-06-10T10:02:00+00:00",
    )

    resolve_tool = AsyncMock(return_value=True)
    resolve_proposal = AsyncMock(return_value=True)
    monkeypatch.setattr(approval_router, "_resolve_tool_call", resolve_tool)
    monkeypatch.setattr(approval_router, "_resolve_reflection_proposal", resolve_proposal)

    assert await approval_router.resolve_approval_request(
        approval_id="tool-1",
        decision="approved",
        approver_user_id="manager-1",
    )
    assert await approval_router.resolve_approval_request(
        approval_id="memory-1",
        decision="approved",
        approver_user_id="manager-2",
    )
    assert await approval_router.resolve_approval_request(
        approval_id="skill-1",
        decision="rejected",
        approver_user_id="manager-3",
    )

    resolve_tool.assert_awaited_once()
    assert resolve_tool.await_args.kwargs["approval_id"] == "tool-1"

    assert resolve_proposal.await_count == 2
    assert [call.kwargs["approval_id"] for call in resolve_proposal.await_args_list] == [
        "memory-1",
        "skill-1",
    ]
    assert resolve_proposal.await_args_list[1].kwargs["decision"] == "rejected"
