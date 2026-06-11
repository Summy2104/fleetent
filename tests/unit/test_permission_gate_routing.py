"""Unit tests for permission_gate routing + outbound (non-blocking suspend model).

Rewritten for approval-suspend-resume: request_approval registers + notifies and
returns "pending" (no blocking wait); resolution is exercised via resolve(). These
tests focus on routing/outbound concerns distinct from test_permission_gate_suspend:
outbound DM to the configured approver, session_id persistence, default-closed when no
approver is reachable, and interactive blocks on the requester prompt + outbound DM.

All tests mock the approval_store + allowlist layers (unit: no real DB).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from fleetent.governance.permission_gate import PermissionGate


def _make_routing(platform: str = "slack", target: str = "U_APPROVER", policy: str = "any"):
    from fleetent.agent_config import ApprovalRouting

    return ApprovalRouting(
        by_risk={"high": {"approvers": [f"{platform}:{target}"], "policy": policy}}
    )


def _make_connectors(platform: str = "slack"):
    connector = AsyncMock()
    connector.conversations_open = AsyncMock(return_value={"channel": {"id": "DM_APPROVER"}})
    connector.chat_postMessage = AsyncMock(return_value={"ok": True})
    return {platform: connector}


def _requester_routing():
    from fleetent.agent_config import ApprovalRouting

    return ApprovalRouting(by_risk={"medium": {"approvers": ["requester"], "policy": "any"}})


@pytest.fixture(autouse=True)
def _mock_store(monkeypatch):
    """Patch approval_store + allowlist_store so unit tests never touch real SQLite."""
    from fleetent.governance import approval_allowlist_store, approval_store

    store_calls: dict = {}

    def _insert(**kw):
        store_calls["insert"] = kw

    monkeypatch.setattr(approval_store, "insert_approval", _insert)
    monkeypatch.setattr(approval_store, "update_approval", MagicMock())
    monkeypatch.setattr(approval_store, "get_approval", MagicMock(return_value=None))
    monkeypatch.setattr(approval_store, "list_approvals", MagicMock(return_value=[]))
    monkeypatch.setattr(approval_allowlist_store, "is_allowed", MagicMock(return_value=False))
    return store_calls


# ── requester ≠ approver: outbound DM to the approver, no self-prompt ──────────


async def test_outbound_approver_is_dmd_and_returns_pending() -> None:
    gate = PermissionGate()
    connectors = _make_connectors()
    reply_calls: list[str] = []

    async def reply(text: str, blocks=None) -> None:
        reply_calls.append(text)

    result = await gate.request_approval(
        approval_id="id1",
        risk_level="high",
        tool_name="delete_db",
        tool_args={},
        requester_user_id="U_REQUESTER",
        reply_func=reply,
        session_id="user:requester",
        approval_routing=_make_routing(),
        outbound_connectors=connectors,
    )

    assert result == "pending"
    connectors["slack"].conversations_open.assert_called_once()
    assert any("⏳" in r or "waiting" in r.lower() for r in reply_calls)
    assert not any("❌" in r for r in reply_calls)
    assert "U_APPROVER" in gate.authorized_actors("id1")


async def test_session_id_passed_to_store(_mock_store) -> None:
    gate = PermissionGate()
    await gate.request_approval(
        approval_id="sess_id",
        risk_level="high",
        tool_name="tool_x",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="user:alice",
        approval_routing=_make_routing(),
        outbound_connectors=_make_connectors(),
    )
    assert _mock_store["insert"]["session_id"] == "user:alice"


# ── default-closed: no reachable approver → rejected immediately ──────────────


async def test_no_approval_routing_is_default_closed_reject() -> None:
    gate = PermissionGate()
    reply_calls: list[str] = []

    async def reply(text: str, blocks=None) -> None:
        reply_calls.append(text)

    result = await gate.request_approval(
        approval_id="no_appr",
        risk_level="high",
        tool_name="tool_y",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=reply,
        session_id="s1",
        approval_routing=None,
        outbound_connectors={},
    )
    assert result == "rejected"
    assert any("❌" in r for r in reply_calls)


async def test_empty_approvers_is_default_closed_reject() -> None:
    from fleetent.agent_config import ApprovalRouting

    gate = PermissionGate()
    routing = ApprovalRouting(by_risk={"high": {"approvers": [], "policy": "any"}})
    result = await gate.request_approval(
        approval_id="empty_appr",
        risk_level="high",
        tool_name="tool_y",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="s2",
        approval_routing=routing,
        outbound_connectors={},
    )
    assert result == "rejected"


async def test_send_failure_triggers_default_closed(monkeypatch) -> None:
    import fleetent.outbound as outbound_mod

    monkeypatch.setattr(outbound_mod, "is_reachable", AsyncMock(return_value=True))
    monkeypatch.setattr(outbound_mod, "send_to", AsyncMock(return_value=False))
    gate = PermissionGate()
    result = await gate.request_approval(
        approval_id="send_fail",
        risk_level="high",
        tool_name="tool_z",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="s3",
        approval_routing=_make_routing(),
        outbound_connectors=_make_connectors(),
    )
    assert result == "rejected"


# ── requester sentinel prompt + interactive blocks ────────────────────────────


async def test_requester_prompt_via_reply_func_without_outbound() -> None:
    gate = PermissionGate()
    connectors = _make_connectors()
    captured: list[dict] = []

    async def reply(text: str, blocks=None) -> None:
        captured.append({"text": text, "blocks": blocks})

    result = await gate.request_approval(
        approval_id="req1",
        risk_level="medium",
        tool_name="send_im_message",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=reply,
        session_id="s1",
        approval_routing=_requester_routing(),
        outbound_connectors=connectors,
    )

    assert result == "pending"
    connectors["slack"].conversations_open.assert_not_called()
    prompt = next(c for c in captured if "approve req1" in c["text"])
    action_ids = {
        e["action_id"]
        for b in (prompt["blocks"] or [])
        if b.get("type") == "actions"
        for e in b["elements"]
    }
    assert "approval_approve" in action_ids


async def test_requester_prompt_degrades_when_reply_func_rejects_blocks() -> None:
    gate = PermissionGate()
    texts: list[str] = []

    async def reply(text: str) -> None:  # no blocks kwarg → TypeError on rich call
        texts.append(text)

    result = await gate.request_approval(
        approval_id="req2",
        risk_level="medium",
        tool_name="send_im_message",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=reply,
        session_id="s1",
        approval_routing=_requester_routing(),
        outbound_connectors={},
    )

    assert result == "pending"
    assert any("approve req2" in t for t in texts)


async def test_outbound_approver_dm_carries_blocks() -> None:
    gate = PermissionGate()
    connectors = _make_connectors()
    result = await gate.request_approval(
        approval_id="blk3",
        risk_level="high",
        tool_name="delete_db",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="s3",
        approval_routing=_make_routing(),
        outbound_connectors=connectors,
    )
    assert result == "pending"
    kwargs = connectors["slack"].chat_postMessage.call_args.kwargs
    assert kwargs.get("blocks"), "approver DM must carry interactive blocks"
