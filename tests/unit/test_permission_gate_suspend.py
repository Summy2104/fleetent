"""Unit tests for the non-blocking (suspend-style) permission gate.

approval-suspend-resume: request_approval registers + notifies + returns "pending"
immediately (no asyncio.Event wait); resolve finalizes the approval record without a
waiter. Auto-approve (allowlist) and no-approver (default-closed) stay terminal.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from fleetent.governance.permission_gate import PermissionGate


@pytest.fixture(autouse=True)
def _mock_store(monkeypatch):
    from fleetent.governance import approval_store
    from fleetent.governance import tool_auto_approvals_store as allowlist

    monkeypatch.setattr(approval_store, "insert_approval", MagicMock())
    monkeypatch.setattr(approval_store, "update_approval", MagicMock())
    # Post-removal resolve() falls back to the store; unit tests have no DB, so a
    # resolved/unknown id reads as "not pending" (None).
    monkeypatch.setattr(approval_store, "get_approval", MagicMock(return_value=None))
    monkeypatch.setattr(allowlist, "is_allowed", lambda fp, **kw: False)
    monkeypatch.setattr(allowlist, "add_grant", MagicMock())


def _requester_routing():
    from fleetent.agent_config import ApprovalRouting

    return ApprovalRouting(by_risk={"medium": {"approvers": ["requester"], "policy": "any"}})


def _outbound_routing(target="U_APPROVER"):
    from fleetent.agent_config import ApprovalRouting

    return ApprovalRouting(by_risk={"high": {"approvers": [f"slack:{target}"], "policy": "any"}})


def _connectors():
    c = AsyncMock()
    c.conversations_open = AsyncMock(return_value={"channel": {"id": "DM"}})
    c.chat_postMessage = AsyncMock(return_value={"ok": True})
    return {"slack": c}


async def test_request_approval_returns_pending_without_blocking() -> None:
    """No resolver runs; request_approval must still return promptly as 'pending'."""
    gate = PermissionGate(medium_timeout=999.0)
    reply = AsyncMock()

    result = await asyncio.wait_for(
        gate.request_approval(
            approval_id="p1",
            risk_level="medium",
            tool_name="send_im_message",
            tool_args={"target": "U2"},
            requester_user_id="U_REQ",
            reply_func=reply,
            session_id="s1",
            approval_routing=_requester_routing(),
            outbound_connectors={},
        ),
        timeout=2.0,  # would hang forever under the old blocking gate
    )

    assert result == "pending"
    reply.assert_awaited()  # prompt was sent


async def test_pending_records_requester_as_authorized_actor() -> None:
    gate = PermissionGate()
    await gate.request_approval(
        approval_id="p2",
        risk_level="medium",
        tool_name="send_im_message",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="s1",
        approval_routing=_requester_routing(),
        outbound_connectors={},
    )
    assert "U_REQ" in gate.authorized_actors("p2")


async def test_pending_records_outbound_approver_as_authorized() -> None:
    gate = PermissionGate()
    await gate.request_approval(
        approval_id="p3",
        risk_level="high",
        tool_name="delete_db",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="s1",
        approval_routing=_outbound_routing("U_APPROVER"),
        outbound_connectors=_connectors(),
    )
    assert "U_APPROVER" in gate.authorized_actors("p3")


async def test_allowlisted_still_auto_approves_immediately(monkeypatch) -> None:
    from fleetent.governance import tool_auto_approvals_store as allowlist

    monkeypatch.setattr(allowlist, "is_allowed", lambda fp, **kw: True)
    gate = PermissionGate()
    result = await gate.request_approval(
        approval_id="p4",
        risk_level="medium",
        tool_name="send_im_message",
        tool_args={"x": 1},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="s1",
        approval_routing=_requester_routing(),
        outbound_connectors={},
    )
    assert result == "approved"


async def test_no_approver_is_default_closed_rejected() -> None:
    gate = PermissionGate()
    result = await gate.request_approval(
        approval_id="p5",
        risk_level="high",
        tool_name="delete_db",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="s1",
        approval_routing=None,
        outbound_connectors={},
    )
    assert result == "rejected"


async def test_resolve_finalizes_pending_and_checks_authorization() -> None:
    gate = PermissionGate()
    await gate.request_approval(
        approval_id="p6",
        risk_level="medium",
        tool_name="send_im_message",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="s1",
        approval_routing=_requester_routing(),
        outbound_connectors={},
    )
    # Unauthorized actor cannot resolve.
    assert await gate.resolve("p6", "approved", approver_user_id="U_OTHER") is False
    # Authorized actor resolves successfully.
    assert await gate.resolve("p6", "approved", approver_user_id="U_REQ") is True
    # Already resolved → no longer pending.
    assert await gate.resolve("p6", "approved", approver_user_id="U_REQ") is False
