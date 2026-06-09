"""Unit tests for permission_gate routing + outbound (tasks 3.4/3.5/3.6/3.7).

Tests:
- Requester ≠ approver: gate contacts configured approver via outbound DM.
- Approval resolved by approval_id from any session (cross-session by approval_id).
- Opaque actor captured in gate decisions (no join to users).
- Default-closed: no approver / send fail / timeout → reject.
- any policy: first resolve decides.
- medium risk uses routing, no self-confirm fallback.

All tests mock the approval_store layer (unit: no real DB).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fleetent.governance.permission_gate import PermissionGate


def _make_routing(platform: str = "slack", target: str = "U_APPROVER", policy: str = "any"):
    from fleetent.agent_config import ApprovalRouting

    return ApprovalRouting(
        by_risk={"high": {"approvers": [f"{platform}:{target}"], "policy": policy}}
    )


def _make_connectors(platform: str = "slack"):
    connector = AsyncMock()
    connector.conversations_open = AsyncMock(
        return_value={"channel": {"id": "DM_APPROVER"}}
    )
    connector.chat_postMessage = AsyncMock(return_value={"ok": True})
    return {platform: connector}


async def _resolve_after(gate, approval_id, decision, actor, delay):
    await asyncio.sleep(delay)
    await gate.resolve(approval_id, decision, actor)


@pytest.fixture(autouse=True)
def _mock_store(monkeypatch):
    """Patch approval_store so unit tests never touch real SQLite."""
    import fleetent.governance.permission_gate as gate_mod
    from fleetent.governance import approval_store

    monkeypatch.setattr(approval_store, "insert_approval", MagicMock())
    monkeypatch.setattr(approval_store, "update_approval", MagicMock())
    monkeypatch.setattr(approval_store, "list_approvals", MagicMock(return_value=[]))
    monkeypatch.setattr(approval_store, "cleanup_stale", MagicMock(return_value=0))


# ── requestor ≠ approver: outbound DM to approver ─────────────────────────────


async def test_gate_contacts_approver_not_requester() -> None:
    """Approver is DM'd via outbound; the requester only gets a 'waiting' notice."""
    gate = PermissionGate(high_timeout=0.2)
    routing = _make_routing()
    connectors = _make_connectors()

    reply_calls: list[str] = []

    async def reply(text: str) -> None:
        reply_calls.append(text)

    asyncio.create_task(_resolve_after(gate, "test_id_1", "approved", "slack:U_APPROVER", 0.01))

    result = await gate.request_approval(
        approval_id="test_id_1",
        risk_level="high",
        tool_name="delete_db",
        tool_args={},
        requester_user_id="U_REQUESTER",
        reply_func=reply,
        session_id="user:requester",
        approval_routing=routing,
        outbound_connectors=connectors,
        high_timeout=0.1,
    )

    assert result == "approved"
    # Approver was DM'd (Slack conversations_open was called)
    connectors["slack"].conversations_open.assert_called_once()
    # Requester got a waiting notice (⏳), not an approval prompt to themselves
    assert any("⏳" in r or "waiting" in r.lower() for r in reply_calls)
    # Requester did NOT get a ❌ (no default-closed rejection)
    assert not any("❌" in r for r in reply_calls)


async def test_gate_resolve_by_approval_id_cross_session() -> None:
    """Resolving by approval_id works regardless of which session the resolve comes from."""
    gate = PermissionGate(high_timeout=0.2)
    routing = _make_routing()
    connectors = _make_connectors()

    asyncio.create_task(_resolve_after(gate, "xsess_id", "approved", "slack:U_APPROVER", 0.01))

    result = await gate.request_approval(
        approval_id="xsess_id",
        risk_level="high",
        tool_name="run_code",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="user:req",
        approval_routing=routing,
        outbound_connectors=connectors,
        high_timeout=0.1,
    )
    assert result == "approved"


# ── opaque actor stored ───────────────────────────────────────────────────────


async def test_approval_actor_stored_as_opaque_string() -> None:
    """Approver actor is stored verbatim as an opaque string, not joined to users."""
    from fleetent.governance import approval_store

    gate = PermissionGate(high_timeout=0.2)
    routing = _make_routing(target="U_OPAQUE")
    connectors = _make_connectors()

    asyncio.create_task(_resolve_after(gate, "opaque_id", "approved", "slack:U_OPAQUE", 0.01))

    await gate.request_approval(
        approval_id="opaque_id",
        risk_level="high",
        tool_name="tool_x",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="user:req",
        approval_routing=routing,
        outbound_connectors=connectors,
        high_timeout=0.1,
    )

    # update_approval called with opaque actor string
    call_kwargs = approval_store.update_approval.call_args.kwargs
    assert call_kwargs["approver_actor"] == "slack:U_OPAQUE"


async def test_session_id_passed_to_store() -> None:
    """session_id must be written to store (not empty string — bug fix)."""
    from fleetent.governance import approval_store

    gate = PermissionGate(high_timeout=0.2)
    routing = _make_routing()
    connectors = _make_connectors()

    asyncio.create_task(_resolve_after(gate, "sess_id", "approved", "slack:U_APPROVER", 0.01))

    await gate.request_approval(
        approval_id="sess_id",
        risk_level="high",
        tool_name="tool_x",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="user:alice",
        approval_routing=routing,
        outbound_connectors=connectors,
        high_timeout=0.1,
    )

    call_kwargs = approval_store.insert_approval.call_args.kwargs
    assert call_kwargs["session_id"] == "user:alice"
    assert call_kwargs["session_id"] != ""


# ── default-closed: no approver → reject ─────────────────────────────────────


async def test_no_approval_routing_is_default_closed_reject() -> None:
    """approval_routing=None → no approvers → default-closed reject immediately."""
    gate = PermissionGate(high_timeout=0.1)

    reply_calls: list[str] = []

    async def reply(text: str) -> None:
        reply_calls.append(text)

    result = await gate.request_approval(
        approval_id="no_approver_1",
        risk_level="high",
        tool_name="tool_y",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=reply,
        session_id="s1",
        approval_routing=None,
        outbound_connectors={},
        high_timeout=0.1,
    )

    assert result == "rejected"
    assert any("❌" in r for r in reply_calls)


async def test_no_approver_in_routing_is_default_closed_reject() -> None:
    """Routing with empty approvers list → default-closed reject."""
    from fleetent.agent_config import ApprovalRouting

    gate = PermissionGate(high_timeout=0.1)
    routing = ApprovalRouting(
        by_risk={"high": {"approvers": [], "policy": "any"}}
    )

    result = await gate.request_approval(
        approval_id="empty_approver_1",
        risk_level="high",
        tool_name="tool_y",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="s2",
        approval_routing=routing,
        outbound_connectors={},
        high_timeout=0.1,
    )

    assert result == "rejected"


async def test_send_failure_triggers_default_closed() -> None:
    """If outbound send fails for all approvers → default-closed reject."""
    from fleetent.agent_config import ApprovalRouting

    gate = PermissionGate(high_timeout=0.1)
    routing = ApprovalRouting(
        by_risk={"high": {"approvers": ["slack:U_UNREACHABLE"], "policy": "any"}}
    )

    # Connector that always fails on send
    bad_connector = AsyncMock()
    bad_connector.conversations_open = AsyncMock(side_effect=RuntimeError("network error"))

    result = await gate.request_approval(
        approval_id="send_fail_1",
        risk_level="high",
        tool_name="tool_z",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="s3",
        approval_routing=routing,
        outbound_connectors={"slack": bad_connector},
        high_timeout=0.1,
    )

    assert result == "rejected"


async def test_timeout_returns_timeout_decision() -> None:
    """No approver response within timeout → 'timeout' decision."""
    gate = PermissionGate(high_timeout=0.05)
    routing = _make_routing()
    connectors = _make_connectors()

    result = await gate.request_approval(
        approval_id="timeout_1",
        risk_level="high",
        tool_name="tool_t",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="s4",
        approval_routing=routing,
        outbound_connectors=connectors,
        high_timeout=0.01,
    )

    assert result == "timeout"


# ── any policy ───────────────────────────────────────────────────────────────


async def test_any_policy_resolves_on_first_approval() -> None:
    """'any' policy: first approver to approve lets the tool through."""
    from fleetent.agent_config import ApprovalRouting

    gate = PermissionGate()
    routing = ApprovalRouting(
        by_risk={
            "high": {
                "approvers": ["slack:U_A", "slack:U_B"],
                "policy": "any",
            }
        }
    )
    connector = AsyncMock()
    connector.conversations_open = AsyncMock(
        return_value={"channel": {"id": "DM"}}
    )
    connector.chat_postMessage = AsyncMock(return_value={"ok": True})

    # Only U_A approves.
    asyncio.create_task(_resolve_after(gate, "any_1", "approved", "slack:U_A", 0.01))

    result = await gate.request_approval(
        approval_id="any_1",
        risk_level="high",
        tool_name="tool_any",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="s5",
        approval_routing=routing,
        outbound_connectors={"slack": connector},
        high_timeout=0.2,
    )

    assert result == "approved"


# ── medium risk uses routing, no self-confirm fallback ────────────────────────


async def test_medium_risk_uses_routing_not_self_confirm() -> None:
    """medium risk: gate contacts configured approver via outbound DM (no self-confirm)."""
    from fleetent.agent_config import ApprovalRouting

    gate = PermissionGate(medium_timeout=0.2)
    routing = ApprovalRouting(
        by_risk={
            "medium": {
                "approvers": ["slack:U_MED"],
                "policy": "any",
            }
        }
    )
    connector = AsyncMock()
    connector.conversations_open = AsyncMock(
        return_value={"channel": {"id": "DM"}}
    )
    connector.chat_postMessage = AsyncMock(return_value={"ok": True})

    asyncio.create_task(_resolve_after(gate, "med_1", "approved", "slack:U_MED", 0.01))

    result = await gate.request_approval(
        approval_id="med_1",
        risk_level="medium",
        tool_name="run_code",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="s6",
        approval_routing=routing,
        outbound_connectors={"slack": connector},
        medium_timeout=0.2,
    )

    assert result == "approved"
    # DM was sent (not a self-confirm prompt to requester)
    connector.conversations_open.assert_called()


async def test_medium_risk_no_routing_is_rejected() -> None:
    """medium risk with no approver config → default-closed reject (no self-confirm fallback)."""
    from fleetent.agent_config import ApprovalRouting

    gate = PermissionGate(medium_timeout=0.1)
    # No medium entry in routing
    routing = ApprovalRouting(
        by_risk={"high": {"approvers": ["slack:U_LEAD"], "policy": "any"}}
    )

    result = await gate.request_approval(
        approval_id="med_noconfig",
        risk_level="medium",
        tool_name="run_code",
        tool_args={},
        requester_user_id="U_REQ",
        reply_func=AsyncMock(),
        session_id="s7",
        approval_routing=routing,
        outbound_connectors={},
        medium_timeout=0.1,
    )

    assert result == "rejected"
