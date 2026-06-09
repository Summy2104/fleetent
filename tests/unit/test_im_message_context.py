"""im-message-context: inject sender/channel/time into the LLM (system frame + user prefix)."""

from __future__ import annotations

import contextlib
from unittest.mock import MagicMock


def _async(value):
    async def _coro():
        return value

    return _coro()


def _agent():
    from fleetent.agent_config import (
        AgentConnectors,
        AgentFile,
        ConnectorAccess,
        SlackConnector,
        default_models,
    )

    return AgentFile(
        name="a",
        version=1,
        models=default_models(),
        connectors=AgentConnectors(
            slack=SlackConnector(
                bot_token_env="BOT",
                app_token_env="APP",
                access=ConnectorAccess(allow_all_users=True),
            )
        ),
    )


async def _route_and_capture(monkeypatch, session_context):
    from fleetent.im_gateway import access, normalizer
    from fleetent.runtime import loop as agent_loop
    from fleetent.session import manager as session_mgr

    monkeypatch.setattr(normalizer, "get_agent_for_context", lambda *a, **k: _agent())
    monkeypatch.setattr(access, "APPROVALS_PATH", MagicMock())
    # Deterministic date/tz.
    monkeypatch.setattr(normalizer, "_current_date_tz", lambda: ("2026-06-09 (Monday)", "UTC"))

    captured: dict = {}

    async def fake_run(**kwargs):
        captured.update(kwargs)
        return "ok"

    @contextlib.asynccontextmanager
    async def fake_lock(sid):
        yield

    monkeypatch.setattr(session_mgr, "session_lock", fake_lock)
    monkeypatch.setattr(session_mgr, "load", lambda _sid: _async([]))
    monkeypatch.setattr(session_mgr, "load_meta", lambda _sid: _async({}))
    monkeypatch.setattr(session_mgr, "save", lambda *a, **k: _async(None))
    monkeypatch.setattr(session_mgr, "is_resume_pending", lambda _sid: False, raising=False)
    monkeypatch.setattr(agent_loop, "run", fake_run)
    monkeypatch.setattr(
        "fleetent.im_gateway.normalizer.resolve_identity", lambda p, uid: uid, raising=False
    )
    monkeypatch.setattr(
        "fleetent.im_gateway.access.resolve_identity", lambda p, uid: uid, raising=False
    )

    async def _reply(text: str) -> None:
        pass

    msg = normalizer.NormalizedMessage(
        platform="slack",
        owner_id="",
        session_id="slack:thread:C9:300.3",
        user_id="U123",
        text="原始问题",
        attachments=[],
        reply_func=_reply,
        channel_id="C9",
        session_context=session_context,
    )
    await normalizer.route(msg)
    return captured["messages"]


async def test_session_frame_injected_into_system(monkeypatch):
    from fleetent.im_gateway.normalizer import SessionContext

    sc = SessionContext(
        platform="slack", sender_id="U123", chat_type="channel", channel_name="C9"
    )
    messages = await _route_and_capture(monkeypatch, sc)
    system = messages[0]
    assert system["role"] == "system"
    assert "slack" in system["content"]
    assert "C9" in system["content"]  # channel surfaced
    assert "2026-06-09" in system["content"]  # date
    assert "UTC" in system["content"]  # timezone


async def test_sender_prefix_injected_into_user(monkeypatch):
    from fleetent.im_gateway.normalizer import SessionContext

    sc = SessionContext(
        platform="slack", sender_id="U123", sender_name="张洋", chat_type="channel"
    )
    messages = await _route_and_capture(monkeypatch, sc)
    user = [m for m in messages if m.get("role") == "user"][-1]
    assert "U123" in user["content"]  # sender id in prefix
    assert "原始问题" in user["content"]  # original text retained


async def test_no_session_context_no_injection(monkeypatch):
    messages = await _route_and_capture(monkeypatch, None)
    system = messages[0]
    user = [m for m in messages if m.get("role") == "user"][-1]
    assert "当前日期" not in system["content"]
    assert user["content"] == "原始问题"  # unchanged
