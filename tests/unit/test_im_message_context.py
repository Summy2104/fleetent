"""im-message-context: inject sender/channel/time into the LLM (system frame + user prefix)."""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock


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

    sc = SessionContext(platform="slack", sender_id="U123", chat_type="channel", channel_name="C9")
    messages = await _route_and_capture(monkeypatch, sc)
    system = messages[0]
    assert system["role"] == "system"
    assert "slack" in system["content"]
    assert "C9" in system["content"]  # channel surfaced
    assert "2026-06-09" in system["content"]  # date
    assert "UTC" in system["content"]  # timezone


async def test_sender_prefix_injected_into_user(monkeypatch):
    from fleetent.im_gateway.normalizer import SessionContext

    sc = SessionContext(platform="slack", sender_id="U123", sender_name="张洋", chat_type="channel")
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


# ── whoami tool ──────────────────────────────────────────────────────────────


def test_whoami_returns_sender():
    from fleetent.im_gateway.normalizer import SessionContext
    from fleetent.tools.builtin_tools import whoami
    from fleetent.tools.registry import ToolContext

    sc = SessionContext(
        platform="slack",
        sender_id="U123",
        sender_name="张洋",
        chat_type="channel",
        channel_name="C9",
    )
    out = whoami(tool_context=ToolContext(session_context=sc))
    assert "U123" in out
    assert "张洋" in out
    assert "slack" in out


def test_whoami_degrades_without_context():
    from fleetent.tools.builtin_tools import whoami
    from fleetent.tools.registry import ToolContext

    out = whoami(tool_context=ToolContext())
    assert "未知" in out or "unknown" in out.lower()
    # must not raise even with no tool_context at all
    assert isinstance(whoami(tool_context=None), str)


async def test_run_threads_session_context_to_tool(monkeypatch):
    """run(session_context=...) reaches the tool via ToolContext at dispatch time."""
    import fleetent.runtime.loop as al
    from fleetent.im_gateway.normalizer import SessionContext

    sc = SessionContext(platform="slack", sender_id="U777")
    captured: dict = {}

    def fake_dispatch(name, args, **kw):
        captured["tool_context"] = kw.get("tool_context")
        return f"{name}_result"

    def _tool_resp():
        tc = MagicMock()
        tc.id = "tc-1"
        tc.function.name = "web_search"
        tc.function.arguments = "{}"
        m = MagicMock()
        m.content = None
        m.tool_calls = [tc]
        m.model_dump = lambda: {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "tc-1",
                    "type": "function",
                    "function": {"name": "web_search", "arguments": "{}"},
                }
            ],
        }
        ch = MagicMock()
        ch.finish_reason = "tool_calls"
        ch.message = m
        r = MagicMock()
        r.choices = [ch]
        r.usage = MagicMock()
        return r

    def _text_resp():
        m = MagicMock()
        m.content = "done"
        m.tool_calls = None
        m.model_dump = lambda: {"role": "assistant", "content": "done"}
        ch = MagicMock()
        ch.finish_reason = "stop"
        ch.message = m
        r = MagicMock()
        r.choices = [ch]
        r.usage = MagicMock()
        return r

    n = 0

    async def fake_create(**kwargs):
        nonlocal n
        n += 1
        return _tool_resp() if n == 1 else _text_resp()

    def _client():
        c = AsyncMock()
        c.chat = MagicMock()
        c.chat.completions = MagicMock()
        c.chat.completions.create = AsyncMock(side_effect=fake_create)
        return c

    monkeypatch.setattr(
        al,
        "get_schemas",
        lambda: [{"type": "function", "function": {"name": "web_search", "parameters": {}}}],
    )
    monkeypatch.setattr(al, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(al, "extract_and_update", AsyncMock())
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (50, 3),
    )
    monkeypatch.setattr(al, "_build_async_client", lambda r, k: _client())
    monkeypatch.setattr(al, "build_context", AsyncMock(return_value=MagicMock(text="", sources=[])))
    monkeypatch.setattr(al, "record_trace_event", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr(al, "dispatch", fake_dispatch)

    result = await al.run(messages=[{"role": "user", "content": "hi"}], session_context=sc)
    assert result == "done"
    assert captured["tool_context"] is not None
    assert captured["tool_context"].session_context is sc


async def test_run_threads_outbound_connectors_to_tool(monkeypatch):
    """run(outbound_connectors=...) reaches the tool via ToolContext at dispatch time."""
    import fleetent.runtime.loop as al

    connector = object()
    captured: dict = {}

    def fake_dispatch(name, args, **kw):
        captured["tool_context"] = kw.get("tool_context")
        return f"{name}_result"

    def _tool_resp():
        tc = MagicMock()
        tc.id = "tc-1"
        tc.function.name = "web_search"
        tc.function.arguments = "{}"
        m = MagicMock()
        m.content = None
        m.tool_calls = [tc]
        m.model_dump = lambda: {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "tc-1",
                    "type": "function",
                    "function": {"name": "web_search", "arguments": "{}"},
                }
            ],
        }
        ch = MagicMock()
        ch.finish_reason = "tool_calls"
        ch.message = m
        r = MagicMock()
        r.choices = [ch]
        r.usage = MagicMock()
        return r

    def _text_resp():
        m = MagicMock()
        m.content = "done"
        m.tool_calls = None
        m.model_dump = lambda: {"role": "assistant", "content": "done"}
        ch = MagicMock()
        ch.finish_reason = "stop"
        ch.message = m
        r = MagicMock()
        r.choices = [ch]
        r.usage = MagicMock()
        return r

    n = 0

    async def fake_create(**kwargs):
        nonlocal n
        n += 1
        return _tool_resp() if n == 1 else _text_resp()

    def _client():
        c = AsyncMock()
        c.chat = MagicMock()
        c.chat.completions = MagicMock()
        c.chat.completions.create = AsyncMock(side_effect=fake_create)
        return c

    monkeypatch.setattr(
        al,
        "get_schemas",
        lambda: [{"type": "function", "function": {"name": "web_search", "parameters": {}}}],
    )
    monkeypatch.setattr(al, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(al, "extract_and_update", AsyncMock())
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (50, 3),
    )
    monkeypatch.setattr(al, "_build_async_client", lambda r, k: _client())
    monkeypatch.setattr(al, "build_context", AsyncMock(return_value=MagicMock(text="", sources=[])))
    monkeypatch.setattr(al, "record_trace_event", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr(al, "dispatch", fake_dispatch)

    result = await al.run(
        messages=[{"role": "user", "content": "hi"}],
        outbound_connectors={"slack": connector},
    )
    assert result == "done"
    assert captured["tool_context"].outbound_connectors["slack"] is connector
