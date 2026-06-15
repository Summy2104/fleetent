"""Integration contract: every resume entry rebuilds its delivery context from the
PERSISTED ConversationAddress, not from the message/click that triggered the resume.

`_resume_pending_in_session` is the single convergence point for the Slack button, the
`approve/reject` text command, and restart recovery — so driving it with a deliberately
WRONG triggering context (top-level DM, no thread) while the pending entry's address is a
thread proves all three entries land output at the persisted address.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import fleetent.outbound as outbound
from fleetent.im_gateway import normalizer
from fleetent.im_gateway.normalizer import NormalizedMessage, SessionContext
from fleetent.outbound import ConversationAddress
from fleetent.runtime import loop as agent_loop
from fleetent.session import manager as session_mgr


@pytest.fixture
def _resume_env(monkeypatch, tmp_path):
    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path)
    # The resumed tool dispatch + loop continuation are mocked; we assert on the
    # delivery context handed to them, not on real execution.
    import fleetent.runtime.approval_resume as ar

    monkeypatch.setattr(ar, "dispatch", lambda name, args, **kw: "ok")
    monkeypatch.setattr(ar, "get_risk_level", lambda name: "medium", raising=False)

    captured: dict = {}

    async def fake_run(**kw):
        captured.update(kw)
        return "继续完成"

    monkeypatch.setattr(agent_loop, "run", fake_run)
    return captured


async def _seed_pending(session_id: str, address: ConversationAddress | None):
    entry: dict = {
        "approval_id": "a1",
        "tool_call_id": "tc1",
        "tool_name": "send_im_message",
        "tool_args": {"target": "U2", "text": "hi"},
        "risk": "medium",
        "approver_ids": ["U1"],
    }
    if address is not None:
        entry["address"] = address.to_dict()
    await session_mgr.add_pending_approval(session_id, "a1", entry)
    await session_mgr.save(session_id, [{"role": "user", "content": "hi"}])


def _wrong_context_msg() -> NormalizedMessage:
    # Triggering message is at top-level DM with NO thread — the bug's source.
    return NormalizedMessage(
        platform="slack",
        session_id="trigger-session",
        user_id="U1",
        text="approve a1",
        attachments=[],
        reply_func=AsyncMock(),
        outbound_connectors={"slack": object()},
        session_context=SessionContext(platform="slack", sender_id="U1", chat_type="dm"),
    )


@pytest.mark.parametrize("decision", ["approved", "rejected"])
async def test_resume_rebuilds_context_from_persisted_thread_address(
    _resume_env, monkeypatch, decision
):
    captured = _resume_env
    address = ConversationAddress(
        platform="slack",
        chat_id="C_THREAD",
        target_type="channel",
        thread_id="170.5",
        user_id="U1",
        chat_type="channel",
        thread_root="170.5",
    )
    await _seed_pending("run-session", address)

    sent: list[dict] = []

    async def fake_send_to(platform, connector, target, text, **kw):
        sent.append({"target": target, **kw})
        return True

    monkeypatch.setattr(outbound, "send_to", fake_send_to)

    await normalizer._resume_pending_in_session(_wrong_context_msg(), "run-session", "a1", decision)

    # 1) chat_type 保真 + SessionContext 从持久化地址还原
    sc = captured["session_context"]
    assert sc.chat_type == "channel"
    assert sc.thread_root == "170.5"
    # 2) conversation_address 透传（re-suspend 时仍能持久化，切断衰减链）
    assert captured["conversation_address"].thread_id == "170.5"
    # 3) progress 可用
    assert captured["progress_func"] is not None
    # 4) reply 回原 thread：重建的 reply_func 经 send_to 携带 thread
    await captured["reply_func"]("done")
    assert sent and sent[0]["target"] == "C_THREAD"
    assert sent[0]["thread"] == "170.5"


async def test_resume_final_reply_posts_to_persisted_address_not_trigger(_resume_env, monkeypatch):
    """The resume's final reply (incl. the 📬 receipt) MUST land in the original conversation
    via the persisted-address replier — NOT via the approve action's reply_func (which would
    drop it at the channel top-level / a fresh DM)."""
    address = ConversationAddress(
        platform="slack",
        chat_id="C_THREAD",
        target_type="channel",
        thread_id="170.5",
        user_id="U1",
        chat_type="channel",
        thread_root="170.5",
    )
    await _seed_pending("run-session", address)

    posted: list[dict] = []

    async def fake_send_to(platform, connector, target, text, **kw):
        posted.append({"target": target, "text": text, **kw})
        return True

    monkeypatch.setattr(outbound, "send_to", fake_send_to)

    msg = _wrong_context_msg()  # trigger is top-level DM with a DISTINCT reply_func
    await normalizer._resume_pending_in_session(msg, "run-session", "a1", "approved")

    # The continuation's final reply ("继续完成" from the mocked run) is delivered to the
    # PERSISTED thread address, threaded — not the triggering approve context.
    finals = [p for p in posted if p["text"] == "继续完成"]
    assert finals, "resume final reply was not posted to the persisted address"
    assert finals[0]["target"] == "C_THREAD"
    assert finals[0]["thread"] == "170.5"
    # The approve action's own reply_func MUST NOT be used for the resume reply.
    msg.reply_func.assert_not_awaited()


async def test_resume_missing_address_degrades_with_warning(_resume_env, monkeypatch, caplog):
    captured = _resume_env
    await _seed_pending("legacy-session", None)  # upgrade-era entry, no address

    warnings: list[str] = []
    monkeypatch.setattr(
        normalizer.logger,
        "warning",
        lambda event, **kw: warnings.append(event),
    )

    msg = _wrong_context_msg()
    await normalizer._resume_pending_in_session(msg, "legacy-session", "a1", "approved")

    # Degrades to the triggering message's context (DM, no thread) and warns — never blocks.
    assert captured["session_context"] is msg.session_context
    assert captured["conversation_address"] is None
    assert any("missing_address" in w for w in warnings)
