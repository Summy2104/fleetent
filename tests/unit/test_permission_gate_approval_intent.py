"""Unit: permission_gate emits a platform-neutral ApprovalPrompt intent (governance de-leak).

The gate MUST NOT construct Slack Block Kit; it passes a neutral ``ApprovalPrompt`` to
reply_func / send_to, and the outbound boundary renders per platform (Slack Block Kit
unchanged; Telegram inline keyboard). All store/allowlist layers mocked (no real DB).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from fleetent.governance.permission_gate import PermissionGate
from fleetent.outbound import ApprovalPrompt, DeliveryReceipt


@pytest.fixture(autouse=True)
def _mock_store(monkeypatch):
    from fleetent.governance import approval_store, tool_auto_approvals_store

    monkeypatch.setattr(approval_store, "insert_approval", MagicMock())
    monkeypatch.setattr(approval_store, "update_approval", MagicMock())
    monkeypatch.setattr(approval_store, "get_approval", MagicMock(return_value=None))
    monkeypatch.setattr(tool_auto_approvals_store, "is_allowed", MagicMock(return_value=False))


def _requester_routing():
    from fleetent.agent_config import ApprovalRouting

    return ApprovalRouting(by_risk={"medium": {"approvers": ["requester"], "policy": "any"}})


def _outbound_routing(platform="slack", target="U_APPROVER"):
    from fleetent.agent_config import ApprovalRouting

    return ApprovalRouting(
        by_risk={"high": {"approvers": [f"{platform}:{target}"], "policy": "any"}}
    )


async def test_gate_does_not_import_block_kit_builder():
    import fleetent.governance.permission_gate as pg

    src = __import__("inspect").getsource(pg)
    assert "approval_prompt_blocks" not in src, "gate must not construct Slack Block Kit"


async def test_requester_prompt_carries_neutral_approval_intent():
    gate = PermissionGate()
    captured: list = []

    async def reply(text, *, approval=None):
        captured.append(approval)

    await gate.request_approval(
        approval_id="id1",
        risk_level="medium",
        tool_name="run_code",
        tool_args={},
        requester_user_id="U1",
        reply_func=reply,
        approval_routing=_requester_routing(),
    )
    assert len(captured) == 1
    ap = captured[0]
    assert isinstance(ap, ApprovalPrompt)
    assert ap.approval_id == "id1"
    assert ap.tool_name == "run_code"


async def test_outbound_approver_send_to_receives_neutral_intent(monkeypatch):
    captured: dict = {}

    async def fake_send_to(platform, connector, target, text, **kw):
        captured["approval"] = kw.get("approval")
        return DeliveryReceipt(
            ok=True, platform=platform, target=target, target_type="user", kind="text"
        )

    monkeypatch.setattr("fleetent.outbound.send_to", fake_send_to)
    monkeypatch.setattr("fleetent.outbound.is_reachable", AsyncMock(return_value=True))

    gate = PermissionGate()
    await gate.request_approval(
        approval_id="id2",
        risk_level="high",
        tool_name="delete_db",
        tool_args={},
        requester_user_id="U1",
        reply_func=AsyncMock(),
        approval_routing=_outbound_routing(),
        outbound_connectors={"slack": AsyncMock()},
    )
    assert isinstance(captured.get("approval"), ApprovalPrompt)
    assert captured["approval"].approval_id == "id2"


async def test_requester_prompt_degrades_when_reply_rejects_approval():
    """A text-only reply_func (no approval kwarg) still gets the plain-text prompt."""
    gate = PermissionGate()
    seen: list = []

    async def reply(text):  # no approval kwarg → TypeError on rich call
        seen.append(text)

    res = await gate.request_approval(
        approval_id="id3",
        risk_level="medium",
        tool_name="run_code",
        tool_args={},
        requester_user_id="U1",
        reply_func=reply,
        approval_routing=_requester_routing(),
    )
    assert res == "pending"
    assert seen and "id3" in seen[0]
