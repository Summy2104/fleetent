"""IM text-command approval resolution drives suspend-resume (Task 7).

When `approve/reject <id>` resolves a pending approval held in the message's session,
the normalizer recovers the authorized actors from the persisted entry, resolves the
gate, and resumes the run via resume_pending_approval. Pieces are mocked (no LLM/DB).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fleetent.im_gateway import normalizer
from fleetent.im_gateway.normalizer import NormalizedMessage, SessionContext


def _msg(text: str) -> NormalizedMessage:
    return NormalizedMessage(
        platform="slack",
        session_id="slack:dm:U_REQ:1.1",
        user_id="U_REQ",
        text=text,
        attachments=[],
        reply_func=AsyncMock(),
        agent_name="my-bot",
        session_context=SessionContext(platform="slack", sender_id="U_REQ"),
        outbound_connectors={"slack": object()},
    )


@pytest.fixture
def _resume_env(monkeypatch):
    from fleetent.governance import approval_router
    from fleetent.session import manager as session_mgr

    entry = {
        "approval_id": "abcd1234",
        "tool_call_id": "tc_1",
        "tool_name": "send_im_message",
        "tool_args": {"target": "U2"},
        "risk": "medium",
        "approver_ids": ["U_REQ"],
    }
    import contextlib

    monkeypatch.setattr(session_mgr, "get_pending_approval", AsyncMock(return_value=dict(entry)))
    monkeypatch.setattr(session_mgr, "load", AsyncMock(return_value=[]))
    monkeypatch.setattr(session_mgr, "save", AsyncMock())

    @contextlib.asynccontextmanager
    async def _noop_lock(_sid):
        yield

    monkeypatch.setattr(session_mgr, "session_lock", _noop_lock)
    resolve = AsyncMock(return_value=True)
    monkeypatch.setattr(approval_router, "resolve_approval_request", resolve)

    resume = AsyncMock(return_value="已帮你把消息发出去了。")
    monkeypatch.setattr(normalizer, "resume_pending_approval", resume, raising=False)

    # Agent resolution: a minimal agent so the continuation kwargs assemble.
    from fleetent.agent_config import AgentFile, default_models

    agent = AgentFile(name="my-bot", version=1, models=default_models())
    monkeypatch.setattr(normalizer.agent_config, "current", lambda: {"my-bot": agent})
    return resolve, resume, entry


async def test_approve_with_pending_resolves_and_resumes(_resume_env):
    resolve, resume, entry = _resume_env
    msg = _msg("approve abcd1234")

    await normalizer.route(msg)

    # Authorization recovered from the persisted entry and passed to resolve.
    assert resolve.await_args.kwargs["approval_id"] == "abcd1234"
    assert resolve.await_args.kwargs["decision"] == "approved"
    assert resolve.await_args.kwargs["authorized_actors"] == {"U_REQ"}
    # Resume invoked for the same session + decision.
    assert resume.await_args.kwargs["session_id"] == "slack:dm:U_REQ:1.1"
    assert resume.await_args.kwargs["approval_id"] == "abcd1234"
    assert resume.await_args.kwargs["decision"] == "approved"
    # Continuation reply delivered to the user.
    msg.reply_func.assert_awaited()


def test_resolve_scope_key_is_public():
    """The workspace scope-key resolver is public API so the resume path (im_gateway)
    can thread it into the resumed tool_context, mirroring a normal turn."""
    from fleetent.runtime import loop

    assert hasattr(loop, "resolve_scope_key")
    assert loop.resolve_scope_key("sess-1", "agentA")  # non-empty for either scope


async def test_resumed_tool_context_carries_scope_key(_resume_env, monkeypatch):
    """The tool_context injected for a resumed (approved) tool must carry the workspace
    scope key, so /workspace arg translation + /exchange attribution apply (regression:
    a scope_key-less resume context silently disabled stdio path translation)."""
    from fleetent.runtime import loop as agent_loop

    monkeypatch.setattr(agent_loop, "resolve_scope_key", lambda sid, an: f"SK::{sid}")
    resolve, resume, entry = _resume_env
    msg = _msg("approve abcd1234")

    await normalizer.route(msg)

    tc = resume.await_args.kwargs["tool_context"]
    assert tc.scope_key == "SK::slack:dm:U_REQ:1.1"


async def test_reject_with_pending_resumes_with_rejected(_resume_env):
    resolve, resume, entry = _resume_env
    msg = _msg("reject abcd1234")

    await normalizer.route(msg)

    assert resolve.await_args.kwargs["decision"] == "rejected"
    assert resume.await_args.kwargs["decision"] == "rejected"


async def test_unauthorized_resolve_does_not_resume(_resume_env, monkeypatch):
    resolve, resume, entry = _resume_env
    # Gate refuses (unauthorized / unknown) → no resume.
    resolve.return_value = False
    msg = _msg("approve abcd1234")

    await normalizer.route(msg)

    resume.assert_not_awaited()
    msg.reply_func.assert_awaited()  # a "not found / unauthorized" notice


async def test_text_approve_uses_run_session_not_message_session(monkeypatch):
    """In a plain DM, the approve command is its own session; the pending lives in the
    ORIGINAL run's session. The handler must resolve the run session from the approval
    row (like the button path), not from the approve message's session."""
    import contextlib

    from fleetent.governance import approval_router, approval_store
    from fleetent.session import manager as session_mgr

    run_session = "slack:dm:U_REQ:1111.0001"  # where the run suspended + stored pending
    entry = {
        "approval_id": "abcd1234",
        "tool_call_id": "tc_1",
        "tool_name": "run_code",
        "tool_args": {"code": "print(1)"},
        "risk": "medium",
        "approver_ids": ["U_REQ"],
    }

    # approval row carries the run's session id.
    monkeypatch.setattr(
        approval_store, "get_approval", lambda aid: {"session_id": run_session, "status": "pending"}
    )

    # get_pending_approval only finds the entry under the RUN session (not the approve msg's).
    async def fake_get_pending(sid, aid):
        return dict(entry) if sid == run_session else None

    monkeypatch.setattr(session_mgr, "get_pending_approval", fake_get_pending)
    monkeypatch.setattr(session_mgr, "load", AsyncMock(return_value=[]))
    monkeypatch.setattr(session_mgr, "save", AsyncMock())

    @contextlib.asynccontextmanager
    async def _noop_lock(_sid):
        yield

    monkeypatch.setattr(session_mgr, "session_lock", _noop_lock)
    monkeypatch.setattr(approval_router, "resolve_approval_request", AsyncMock(return_value=True))

    resume = AsyncMock(return_value="完成")
    monkeypatch.setattr(normalizer, "resume_pending_approval", resume, raising=False)

    from fleetent.agent_config import AgentFile, default_models

    agent = AgentFile(name="my-bot", version=1, models=default_models())
    monkeypatch.setattr(normalizer.agent_config, "current", lambda: {"my-bot": agent})

    # The approve command arrives in a DIFFERENT session than the run.
    msg = NormalizedMessage(
        platform="slack",
        session_id="slack:dm:U_REQ:9999.0009",
        user_id="U_REQ",
        text="approve abcd1234",
        attachments=[],
        reply_func=AsyncMock(),
        agent_name="my-bot",
        session_context=SessionContext(platform="slack", sender_id="U_REQ"),
        outbound_connectors={"slack": object()},
    )
    await normalizer.route(msg)

    # Resume must target the RUN's session, not the approve message's session.
    assert resume.await_args is not None, "resume was not triggered (looked up wrong session)"
    assert resume.await_args.kwargs["session_id"] == run_session


def _approve_msg(connectors: dict) -> NormalizedMessage:
    return NormalizedMessage(
        platform="slack",
        session_id="slack:dm:U_REQ:1.1",
        user_id="U_REQ",
        text="approve abcd1234",
        attachments=[],
        reply_func=AsyncMock(),
        agent_name="my-bot",
        session_context=SessionContext(platform="slack", sender_id="U_REQ"),
        outbound_connectors=connectors,
    )


async def test_resume_managed_empty_connectors_is_failfast_not_proxy(_resume_env, monkeypatch):
    """agent-hosted-im：统一后 managed 与 standalone 同路径，无 ManagedOutboundConnector 代理。

    实际的 managed approve 会由 agent 自持的 slack adapter 注入 live 连接器
    （见 test_resume_managed_runtime_keeps_live_connectors）。若因故连接器缺失，resolve_for_runtime
    fail-fast 返回 {}（记 error、不再伪造队列代理）。
    """
    from fleetent import outbound_connectors as oc

    monkeypatch.setattr(oc, "is_node_managed_runtime", lambda: True)
    _resolve, resume, _entry = _resume_env

    await normalizer.route(_approve_msg({}))  # 无 live 连接器（异常态）

    tc = resume.await_args.kwargs["tool_context"]
    # No fabricated proxy — the miss is surfaced as an empty connector set (fail-fast).
    assert tc.outbound_connectors == {}


async def test_resume_managed_runtime_keeps_live_connectors(_resume_env, monkeypatch):
    """agent-hosted-im：managed 下 agent 自持连接，approve 携带 live 连接器 → 原样直发。"""
    from fleetent import outbound_connectors as oc

    monkeypatch.setattr(oc, "is_node_managed_runtime", lambda: True)
    _resolve, resume, _entry = _resume_env
    sentinel = object()

    await normalizer.route(_approve_msg({"slack": sentinel}))

    tc = resume.await_args.kwargs["tool_context"]
    assert tc.outbound_connectors == {"slack": sentinel}


async def test_resume_standalone_keeps_live_connectors(_resume_env):
    """回归：standalone（msg.outbound_connectors 非空）下 resolve 原样返回 live 连接器。"""
    _resolve, resume, _entry = _resume_env
    sentinel = object()

    await normalizer.route(_approve_msg({"slack": sentinel}))

    tc = resume.await_args.kwargs["tool_context"]
    assert tc.outbound_connectors == {"slack": sentinel}
    assert tc.outbound_connectors["slack"] is sentinel
