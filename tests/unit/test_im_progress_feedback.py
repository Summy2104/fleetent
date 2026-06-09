"""Tests for IM progress feedback: progress_func across normalizer, run(), Slack, Telegram."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

# ── 1. NormalizedMessage.progress_func field ─────────────────────────────────


def test_normalized_message_has_progress_func_field():
    from fleetent.im_gateway.normalizer import NormalizedMessage

    async def _reply(text: str) -> None:
        pass

    msg = NormalizedMessage(
        platform="slack",
        session_id="s1",
        user_id="u1",
        text="hi",
        attachments=[],
        reply_func=_reply,
    )
    assert hasattr(msg, "progress_func")
    assert msg.progress_func is None


def test_normalized_message_progress_func_can_be_set():
    from fleetent.im_gateway.normalizer import NormalizedMessage

    async def _reply(text: str) -> None:
        pass

    async def _progress(event: dict) -> None:
        pass

    msg = NormalizedMessage(
        platform="slack",
        session_id="s1",
        user_id="u1",
        text="hi",
        attachments=[],
        reply_func=_reply,
        progress_func=_progress,
    )
    assert msg.progress_func is _progress


# ── 2. agent_loop.run() progress_func ────────────────────────────────────────


async def test_run_calls_progress_func_on_tool_call(monkeypatch):
    """progress_func receives tool_call event before tool executes."""
    import fleetent.runtime.loop as al

    called: list[dict] = []

    async def progress(event: dict) -> None:
        called.append(event)

    tool_resp = _make_tool_resp("web_search")
    text_resp = _make_text_resp("done")

    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return tool_resp
        return text_resp

    monkeypatch.setattr(al, "get_schemas", lambda: [_fake_schema("web_search")])
    monkeypatch.setattr(al, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(al, "extract_and_update", AsyncMock())
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (50, 3),
    )
    monkeypatch.setattr(
        al,
        "get_async_client_and_config",
        lambda *a, **kw: _mock_client_cfg(fake_create),
        raising=False,
    )
    monkeypatch.setattr(al, "_build_async_client", lambda r, k: _mock_client(fake_create))
    monkeypatch.setattr(al, "build_context", AsyncMock(return_value=MagicMock(text="", sources=[])))
    monkeypatch.setattr(al, "record_trace_event", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr(al, "dispatch", lambda name, args, **kw: f"{name}_result")

    result = await al.run(
        messages=[{"role": "user", "content": "search for something"}],
        progress_func=progress,
    )
    assert result == "done"
    assert len(called) == 1
    # Batch contract: names list carries all tools of the turn; name kept for back-compat.
    assert called[0] == {"type": "tool_call", "names": ["web_search"], "name": "web_search"}


async def test_run_emits_single_batch_event_for_parallel_tools(monkeypatch):
    """A turn with multiple tool_calls emits ONE progress event carrying all names."""
    import fleetent.runtime.loop as al

    called: list[dict] = []

    async def progress(event: dict) -> None:
        called.append(dict(event))

    multi_resp = _make_multi_tool_resp(["web_search", "read_file"])
    text_resp = _make_text_resp("done")
    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        return multi_resp if call_count == 1 else text_resp

    monkeypatch.setattr(
        al, "get_schemas", lambda: [_fake_schema("web_search"), _fake_schema("read_file")]
    )
    _patch_loop_basics(monkeypatch, al, fake_create)

    result = await al.run(
        messages=[{"role": "user", "content": "do two things"}],
        progress_func=progress,
    )
    assert result == "done"
    # Exactly one batch event, listing both tools (not two separate per-tool events).
    assert len(called) == 1
    assert called[0]["type"] == "tool_call"
    assert called[0]["names"] == ["web_search", "read_file"]


async def test_sub_agent_run_does_not_emit_parent_progress(monkeypatch):
    """A sub_agent run (is_sub_agent=True) never surfaces tool batches to progress_func."""
    import fleetent.runtime.loop as al

    called: list[dict] = []

    async def progress(event: dict) -> None:
        called.append(dict(event))

    tool_resp = _make_tool_resp("web_search")
    text_resp = _make_text_resp("done")
    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        return tool_resp if call_count == 1 else text_resp

    _patch_loop_basics(monkeypatch, al, fake_create)

    result = await al.run(
        messages=[{"role": "user", "content": "test"}],
        is_sub_agent=True,
        progress_func=progress,
    )
    assert result == "done"
    assert called == []


async def test_run_progress_func_exception_does_not_interrupt(monkeypatch):
    """progress_func exception is swallowed; run() continues normally."""
    import fleetent.runtime.loop as al

    async def bad_progress(event: dict) -> None:
        raise RuntimeError("network error")

    tool_resp = _make_tool_resp("web_search")
    text_resp = _make_text_resp("done")
    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        return tool_resp if call_count == 1 else text_resp

    _patch_loop_basics(monkeypatch, al, fake_create)

    result = await al.run(
        messages=[{"role": "user", "content": "test"}],
        progress_func=bad_progress,
    )
    assert result == "done"


async def test_run_no_progress_func_unchanged_behavior(monkeypatch):
    """Omitting progress_func has no effect on run()."""
    import fleetent.runtime.loop as al

    text_resp = _make_text_resp("hello")

    async def fake_create(**kwargs):
        return text_resp

    _patch_loop_basics(monkeypatch, al, fake_create)

    result = await al.run(
        messages=[{"role": "user", "content": "hi"}],
    )
    assert result == "hello"


async def test_run_progress_func_only_gets_name_not_args(monkeypatch):
    """Event dict contains only 'type' and 'name', no tool args."""
    import fleetent.runtime.loop as al

    received: list[dict] = []

    async def progress(event: dict) -> None:
        received.append(dict(event))

    tool_resp = _make_tool_resp("web_search", args='{"query": "secret"}')
    text_resp = _make_text_resp("done")
    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        return tool_resp if call_count == 1 else text_resp

    _patch_loop_basics(monkeypatch, al, fake_create)

    await al.run(
        messages=[{"role": "user", "content": "test"}],
        progress_func=progress,
    )
    assert received
    event = received[0]
    assert set(event.keys()) == {"type", "names", "name"}
    assert "args" not in event
    assert "query" not in str(event)


# ── 3. normalizer passes progress_func to run() ──────────────────────────────


async def test_normalizer_passes_progress_func_to_run(monkeypatch):
    """normalizer.route() forwards msg.progress_func to agent_loop.run()."""
    import contextlib

    from fleetent.agent_config import (
        AgentConnectors,
        AgentFile,
        ConnectorAccess,
        SlackConnector,
        default_models,
    )
    from fleetent.im_gateway import access, normalizer
    from fleetent.runtime import loop as agent_loop
    from fleetent.session import manager as session_mgr

    agent = AgentFile(
        name="a",
        version=1,
        models=default_models(),
        connectors=AgentConnectors(
            slack=SlackConnector(
                bot_token_env="BOT",
                app_token_env="APP",
                access=ConnectorAccess(allow_users=["u1"]),
            )
        ),
    )
    monkeypatch.setattr(normalizer, "get_agent_for_context", lambda *a, **k: agent)
    monkeypatch.setattr(access, "APPROVALS_PATH", MagicMock())

    run_kwargs: dict = {}

    async def fake_run(**kwargs):
        run_kwargs.update(kwargs)
        return "ok"

    @contextlib.asynccontextmanager
    async def fake_lock(sid):
        yield

    monkeypatch.setattr(session_mgr, "session_lock", fake_lock)
    monkeypatch.setattr(session_mgr, "load", lambda _sid: _async([]))
    monkeypatch.setattr(session_mgr, "load_meta", lambda _sid: _async({}))
    monkeypatch.setattr(session_mgr, "save", lambda *a, **k: _async(None))
    monkeypatch.setattr(agent_loop, "run", fake_run)
    # Patch resolve_identity so it doesn't hit DB
    monkeypatch.setattr(
        "fleetent.im_gateway.normalizer.resolve_identity", lambda p, uid: uid, raising=False
    )
    monkeypatch.setattr(
        "fleetent.im_gateway.access.resolve_identity", lambda p, uid: uid, raising=False
    )

    async def _reply(text: str) -> None:
        pass

    async def _progress(event: dict) -> None:
        pass

    msg = normalizer.NormalizedMessage(
        platform="slack",
        owner_id="",
        session_id="s1",
        user_id="u1",
        text="hi",
        attachments=[],
        reply_func=_reply,
        progress_func=_progress,
        channel_id="C1",
    )
    await normalizer.route(msg)
    assert "progress_func" in run_kwargs
    assert run_kwargs["progress_func"] is _progress


async def test_normalizer_without_progress_func_run_gets_none(monkeypatch):
    """When no progress_func set, run() receives None (or omits the kwarg)."""
    import contextlib

    from fleetent.agent_config import (
        AgentConnectors,
        AgentFile,
        ConnectorAccess,
        SlackConnector,
        default_models,
    )
    from fleetent.im_gateway import access, normalizer
    from fleetent.runtime import loop as agent_loop
    from fleetent.session import manager as session_mgr

    agent = AgentFile(
        name="a",
        version=1,
        models=default_models(),
        connectors=AgentConnectors(
            slack=SlackConnector(
                bot_token_env="BOT",
                app_token_env="APP",
                access=ConnectorAccess(allow_users=["u1"]),
            )
        ),
    )
    monkeypatch.setattr(normalizer, "get_agent_for_context", lambda *a, **k: agent)
    monkeypatch.setattr(access, "APPROVALS_PATH", MagicMock())

    run_kwargs: dict = {}

    async def fake_run(**kwargs):
        run_kwargs.update(kwargs)
        return "ok"

    @contextlib.asynccontextmanager
    async def fake_lock(sid):
        yield

    monkeypatch.setattr(session_mgr, "session_lock", fake_lock)
    monkeypatch.setattr(session_mgr, "load", lambda _sid: _async([]))
    monkeypatch.setattr(session_mgr, "load_meta", lambda _sid: _async({}))
    monkeypatch.setattr(session_mgr, "save", lambda *a, **k: _async(None))
    monkeypatch.setattr(agent_loop, "run", fake_run)
    monkeypatch.setattr(
        "fleetent.im_gateway.access.resolve_identity", lambda p, uid: uid, raising=False
    )

    async def _reply(text: str) -> None:
        pass

    msg = normalizer.NormalizedMessage(
        platform="slack",
        owner_id="",
        session_id="s1",
        user_id="u1",
        text="hi",
        attachments=[],
        reply_func=_reply,
        channel_id="C1",
    )
    await normalizer.route(msg)
    # Either key absent or None
    assert run_kwargs.get("progress_func") is None


# ── 5. Telegram adapter ───────────────────────────────────────────────────────


def _telegram_handler(monkeypatch, config=None):
    """Build Telegram handler and capture route calls."""
    import fleetent.im_gateway.telegram as telegram

    if config is None:
        config = {"bot_token": "tg-test"}

    routed: dict = {}

    async def fake_route(msg):
        routed["msg"] = msg

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)

    mock_app = MagicMock()
    mock_builder = MagicMock()
    mock_builder.token.return_value = mock_builder
    mock_builder.concurrent_updates.return_value = mock_builder
    mock_builder.build.return_value = mock_app

    with patch("telegram.ext.Application") as mock_cls:
        mock_cls.builder.return_value = mock_builder
        telegram.create_app("agent1", "ownerA", config)

    handler = mock_app.add_handler.call_args[0][0]
    return handler, routed


def _make_tg_update(chat_id="-100", text="hi"):
    from telegram import Update

    update = MagicMock(spec=Update)
    eff_user = MagicMock()
    eff_user.id = 555
    update.effective_user = eff_user
    msg = MagicMock()
    msg.reply_to_message = None
    chat = MagicMock()
    chat.type = "private"
    chat.id = chat_id
    msg.chat = chat
    msg.caption = None
    msg.text = text
    msg.photo = None
    msg.reply_text = AsyncMock()
    update.message = msg
    return update


async def test_telegram_progress_func_sends_typing_action(monkeypatch):
    """Telegram progress_func calls send_chat_action('typing') on tool_call event."""
    handler, routed = _telegram_handler(monkeypatch)

    update = _make_tg_update("-100", "hello")
    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()

    await handler.callback(update, context)

    msg = routed["msg"]
    assert msg.progress_func is not None

    await msg.progress_func({"type": "tool_call", "name": "web_search"})

    context.bot.send_chat_action.assert_called_once()
    call_args = context.bot.send_chat_action.call_args
    # Check that "typing" action was sent to the correct chat
    assert "typing" in str(call_args).lower()


async def test_telegram_progress_func_handles_batch_event(monkeypatch):
    """Telegram still sends typing on the batch event shape ({"names": [...]})."""
    handler, routed = _telegram_handler(monkeypatch)

    update = _make_tg_update("-100", "hello")
    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()

    await handler.callback(update, context)
    msg = routed["msg"]

    await msg.progress_func({"type": "tool_call", "names": ["web_search", "read_file"]})

    context.bot.send_chat_action.assert_called_once()
    assert "typing" in str(context.bot.send_chat_action.call_args).lower()


async def test_telegram_progress_func_failure_does_not_interrupt(monkeypatch):
    """send_chat_action failure is swallowed; does not propagate."""
    handler, routed = _telegram_handler(monkeypatch)

    update = _make_tg_update("-100", "hello")
    context = MagicMock()
    context.bot.send_chat_action = AsyncMock(side_effect=Exception("telegram error"))

    await handler.callback(update, context)
    msg = routed["msg"]

    # Should not raise
    await msg.progress_func({"type": "tool_call", "name": "web_search"})


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_text_resp(text: str):
    m = MagicMock()
    m.content = text
    m.tool_calls = None
    m.model_dump = lambda: {"role": "assistant", "content": text}
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message = m
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock()
    return resp


def _make_tool_resp(name: str, args: str = "{}"):
    tc = MagicMock()
    tc.id = "tc-1"
    tc.function.name = name
    tc.function.arguments = args
    m = MagicMock()
    m.content = None
    m.tool_calls = [tc]
    m.model_dump = lambda: {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "tc-1", "type": "function", "function": {"name": name, "arguments": args}}
        ],
    }
    choice = MagicMock()
    choice.finish_reason = "tool_calls"
    choice.message = m
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock()
    return resp


def _make_multi_tool_resp(names: list[str]):
    tcs = []
    for i, name in enumerate(names):
        tc = MagicMock()
        tc.id = f"tc-{i}"
        tc.function.name = name
        tc.function.arguments = "{}"
        tcs.append(tc)
    m = MagicMock()
    m.content = None
    m.tool_calls = tcs
    m.model_dump = lambda: {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": f"tc-{i}", "type": "function", "function": {"name": n, "arguments": "{}"}}
            for i, n in enumerate(names)
        ],
    }
    choice = MagicMock()
    choice.finish_reason = "tool_calls"
    choice.message = m
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock()
    return resp


def _fake_schema(name: str) -> dict:
    return {"type": "function", "function": {"name": name, "parameters": {}}}


def _mock_client(fake_create):
    client = AsyncMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=fake_create)
    return client


def _mock_client_cfg(fake_create):
    client = _mock_client(fake_create)
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512
    cfg.params = {}
    cfg.fallbacks = ()
    return client, cfg


def _patch_loop_basics(monkeypatch, al, fake_create):
    monkeypatch.setattr(al, "get_schemas", lambda: [_fake_schema("web_search")])
    monkeypatch.setattr(al, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(al, "extract_and_update", AsyncMock())
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (50, 3),
    )
    monkeypatch.setattr(
        al,
        "get_async_client_and_config",
        lambda *a, **kw: _mock_client_cfg(fake_create),
        raising=False,
    )
    monkeypatch.setattr(al, "_build_async_client", lambda r, k: _mock_client(fake_create))
    monkeypatch.setattr(al, "build_context", AsyncMock(return_value=MagicMock(text="", sources=[])))
    monkeypatch.setattr(al, "record_trace_event", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr(al, "dispatch", lambda name, args, **kw: f"{name}_result")


def _async(value):
    async def _coro():
        return value

    return _coro()
