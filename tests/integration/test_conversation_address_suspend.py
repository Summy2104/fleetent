"""Integration: a suspended run persists its ConversationAddress into the pending entry,
and the session manager round-trips entries with and without an address (upgrade compat).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.runtime.loop as al
from fleetent.identity import Principal
from fleetent.outbound import ConversationAddress
from fleetent.session import manager as session_mgr


def _governance():
    from fleetent.runtime.snapshot import GovernanceConfig

    return GovernanceConfig()


def _requester_routing():
    from fleetent.agent_config import ApprovalRouting

    return ApprovalRouting(by_risk={"medium": {"approvers": ["requester"], "policy": "any"}})


def _tool_call_response(name: str, args: str = "{}"):
    tc = MagicMock()
    tc.id = "tc_1"
    tc.function.name = name
    tc.function.arguments = args
    m = MagicMock()
    m.content = None
    m.tool_calls = [tc]
    m.model_dump = lambda: {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "tc_1", "type": "function", "function": {"name": name, "arguments": args}}
        ],
    }
    ch = MagicMock()
    ch.finish_reason = "tool_calls"
    ch.message = m
    r = MagicMock()
    r.choices = [ch]
    r.usage = MagicMock()
    return r


@pytest.fixture
def _suspend_env(monkeypatch, tmp_path):
    from fleetent.governance import approval_allowlist_store as allowlist
    from fleetent.governance import approval_store

    async def fake_create(**kwargs):
        return _tool_call_response("send_im_message", '{"target": "U2", "text": "hi"}')

    def _client():
        c = AsyncMock()
        c.chat = MagicMock()
        c.chat.completions = MagicMock()
        c.chat.completions.create = AsyncMock(side_effect=fake_create)
        return c

    monkeypatch.setattr(
        al,
        "get_schemas",
        lambda: [{"type": "function", "function": {"name": "send_im_message", "parameters": {}}}],
    )
    monkeypatch.setattr(al, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(al, "extract_and_update", AsyncMock())
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(al, "collect_disabled_trace", lambda *a, **k: None)
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (50, 3),
    )
    monkeypatch.setattr(al, "_build_async_client", lambda r, k: _client())
    monkeypatch.setattr(al, "build_context", AsyncMock(return_value=MagicMock(text="", sources=[])))
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(approval_store, "insert_approval", MagicMock())
    monkeypatch.setattr(approval_store, "update_approval", MagicMock())
    monkeypatch.setattr(allowlist, "is_allowed", lambda fp, **kw: False)
    # Real session manager, isolated to tmp.
    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path)
    return al


async def test_suspend_persists_address_into_pending_entry(_suspend_env):
    address = ConversationAddress(
        platform="slack",
        chat_id="C_THREAD",
        target_type="channel",
        thread_id="170.5",
        user_id="U_REQ",
        chat_type="channel",
        thread_root="170.5",
    )

    await al.run(
        messages=[{"role": "user", "content": "send to U2"}],
        reply_func=AsyncMock(),
        principal=Principal(user_id="U_REQ", tenant_id="default"),
        session_id="slack:C_THREAD:170.5",
        governance=_governance(),
        approval_routing=_requester_routing(),
        permission_gate_enabled=True,
        conversation_address=address,
    )

    pending_map = await _read_pending("slack:C_THREAD:170.5")
    assert len(pending_map) == 1
    entry = next(iter(pending_map.values()))
    assert entry["address"]["platform"] == "slack"
    assert entry["address"]["chat_id"] == "C_THREAD"
    assert entry["address"]["thread_id"] == "170.5"
    assert entry["address"]["chat_type"] == "channel"
    assert entry["tool_name"] == "send_im_message"


async def test_old_pending_entry_without_address_reads_without_crash(_suspend_env):
    # Simulate an upgrade-era entry persisted before address existed.
    await session_mgr.add_pending_approval(
        "slack:legacy:1",
        "old1",
        {"approval_id": "old1", "tool_call_id": "tc_x", "tool_name": "t", "risk": "medium"},
    )
    entry = await session_mgr.get_pending_approval("slack:legacy:1", "old1")
    assert entry is not None
    assert entry.get("address") is None
    assert entry["tool_name"] == "t"


async def _read_pending(session_id: str) -> dict:
    meta = await session_mgr.load_meta(session_id)
    return dict(meta.get("pending_approvals", {}))
