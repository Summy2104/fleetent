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
    from fleetent.governance.permission_gate import _default_gate
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
    monkeypatch.setattr(_default_gate, "resolve", resolve)

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
