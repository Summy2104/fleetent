"""Unit tests for agent_loop.run() and run_stream()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIStatusError, RateLimitError

import fleetent.agent_loop as al
from fleetent.model_router import RouteConfig

# ── helpers ──────────────────────────────────────────────────────────────────


def _text_resp(text: str | None = "reply") -> MagicMock:
    msg = MagicMock()
    msg.content = text
    msg.tool_calls = None

    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock()
    return resp


def _tool_resp(name: str, args: str = "{}", call_id: str = "tc-1") -> MagicMock:
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = args

    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]

    choice = MagicMock()
    choice.finish_reason = "tool_calls"
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock()
    return resp


async def _stream_chunks(*contents: str | None, finish: str = "stop"):
    """Async generator yielding fake stream chunks. Last chunk gets finish_reason."""
    for i, content in enumerate(contents):
        c = MagicMock()
        c.usage = None
        c.choices = [MagicMock()]
        c.choices[0].delta.content = content
        c.choices[0].delta.tool_calls = None
        c.choices[0].finish_reason = finish if i == len(contents) - 1 else None
        yield c


async def _stream_chunks_with_usage(prompt: int, completion: int, *contents: str | None):
    """Like _stream_chunks but appends a usage-only chunk (no choices) at the end."""
    async for chunk in _stream_chunks(*contents):
        yield chunk
    u = MagicMock()
    u.choices = []
    u.usage = MagicMock()
    u.usage.prompt_tokens = prompt
    u.usage.completion_tokens = completion
    u.usage.total_tokens = prompt + completion
    yield u


@pytest.fixture
def mock_client(monkeypatch) -> AsyncMock:
    """Patch all external I/O in agent_loop, return the mock LLM client."""
    from fleetent.intelligence.long_term_ctx import BuiltContext

    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512

    cfg.fallbacks = ()

    monkeypatch.setattr(al, "get_async_client_and_config", lambda _: (client, cfg))
    monkeypatch.setattr(al, "get_schemas", lambda: [])
    monkeypatch.setattr(al, "maybe_compress", lambda msgs: msgs)
    monkeypatch.setattr(al, "record_trace_event", lambda event: None)
    monkeypatch.setattr(al, "dispatch", lambda name, args, **kw: f"{name}_result")
    monkeypatch.setattr(al, "match_skill", lambda _: None)
    monkeypatch.setattr(
        al, "build_context", AsyncMock(return_value=BuiltContext(text="", sources=[]))
    )
    return client


# ── run() ────────────────────────────────────────────────────────────────────


async def test_run_returns_text_reply(mock_client):
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("hello"))
    result = await al.run([{"role": "user", "content": "hi"}])
    assert result == "hello"


async def test_run_returns_empty_string_when_content_is_none(mock_client):
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp(None))
    result = await al.run([{"role": "user", "content": "hi"}])
    assert result == ""


async def test_run_dispatches_tool_then_gets_final_reply(mock_client):
    dispatched: list[str] = []

    mock_client.chat.completions.create = AsyncMock(
        side_effect=[_tool_resp("get_time"), _text_resp("it is noon")]
    )

    def capture_dispatch(name: str, args: str, **kw) -> str:
        dispatched.append(name)
        return f"{name}_result"

    with patch.object(al, "dispatch", capture_dispatch):
        result = await al.run([{"role": "user", "content": "what time?"}])

    assert result == "it is noon"
    assert dispatched == ["get_time"]
    assert mock_client.chat.completions.create.call_count == 2


async def test_run_is_sub_agent_filters_sub_agent_from_schemas(mock_client):
    schemas_used: list[list] = []

    async def capture(**kwargs):
        schemas_used.append(kwargs.get("tools", []))
        return _text_resp("ok")

    mock_client.chat.completions.create = capture

    with patch.object(
        al,
        "get_schemas",
        return_value=[
            {"function": {"name": "sub_agent"}},
            {"function": {"name": "get_time"}},
        ],
    ):
        await al.run([{"role": "user", "content": "go"}], is_sub_agent=True)

    names = [s["function"]["name"] for s in schemas_used[0]]
    assert "sub_agent" not in names
    assert "get_time" in names


async def test_run_not_sub_agent_includes_sub_agent_in_schemas(mock_client):
    schemas_used: list[list] = []

    async def capture(**kwargs):
        schemas_used.append(kwargs.get("tools", []))
        return _text_resp("ok")

    mock_client.chat.completions.create = capture

    with patch.object(
        al,
        "get_schemas",
        return_value=[
            {"function": {"name": "sub_agent"}},
            {"function": {"name": "get_time"}},
        ],
    ):
        await al.run([{"role": "user", "content": "go"}])

    names = [s["function"]["name"] for s in schemas_used[0]]
    assert "sub_agent" in names


async def test_run_injects_long_term_context_before_model_call(mock_client, monkeypatch):
    from fleetent.intelligence.long_term_ctx import BuiltContext

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    build_context = AsyncMock(
        return_value=BuiltContext(text="Remember user preference", sources=[])
    )
    monkeypatch.setattr(al, "build_context", build_context)

    await al.run(
        [
            {"role": "system", "content": "base system"},
            {"role": "user", "content": "what should I use?"},
        ],
        user_id="user-1",
        agent_name="agent-1",
    )

    build_context.assert_awaited_once_with(
        "user-1",
        "what should I use?",
        "agent-1",
        512,
    )
    messages = mock_client.chat.completions.create.await_args.kwargs["messages"]
    assert messages[0]["content"] == "base system\n\n[Long-term context]\nRemember user preference"


# ── run_stream() ──────────────────────────────────────────────────────────────


async def test_run_stream_yields_text_deltas_and_done(mock_client):
    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("hel", "lo", None))

    events = [e async for e in al.run_stream("say hello")]

    deltas = [e["content"] for e in events if e["type"] == "text_delta"]
    assert deltas == ["hel", "lo"]
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    assert done[0]["content"] == "hello"


async def test_run_stream_does_not_inject_memory_prompt(mock_client):
    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("hello"))

    [_ async for _ in al.run_stream("say hello")]

    messages = mock_client.chat.completions.create.await_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "[Memory]" not in messages[0]["content"]


async def test_run_stream_done_on_empty_response(mock_client):
    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks(None))

    events = [e async for e in al.run_stream("hi")]

    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    assert done[0]["content"] == ""


async def test_run_stream_tool_call_yields_tool_events(mock_client):
    async def tool_stream():
        c = MagicMock()
        c.choices = [MagicMock()]
        c.choices[0].delta.content = None
        tc_delta = MagicMock()
        tc_delta.index = 0
        tc_delta.id = "tc-1"
        tc_delta.function.name = "get_time"
        tc_delta.function.arguments = "{}"
        c.choices[0].delta.tool_calls = [tc_delta]
        c.choices[0].finish_reason = "tool_calls"
        yield c

    async def text_stream():
        c = MagicMock()
        c.choices = [MagicMock()]
        c.choices[0].delta.content = "12:00"
        c.choices[0].delta.tool_calls = None
        c.choices[0].finish_reason = "stop"
        yield c

    mock_client.chat.completions.create = AsyncMock(side_effect=[tool_stream(), text_stream()])

    events = [e async for e in al.run_stream("what time?")]

    types = [e["type"] for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    assert "text_delta" in types
    assert "done" in types

    tool_event = next(e for e in events if e["type"] == "tool_call")
    assert tool_event["name"] == "get_time"


async def test_run_stream_injects_long_term_context_before_model_call(mock_client, monkeypatch):
    from fleetent.intelligence.long_term_ctx import BuiltContext

    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok"))
    build_context = AsyncMock(
        return_value=BuiltContext(text="Use private deployment docs", sources=[])
    )
    monkeypatch.setattr(al, "build_context", build_context)

    [_ async for _ in al.run_stream("how deploy?", user_id="user-1", agent_name="agent-1")]

    build_context.assert_awaited_once_with("user-1", "how deploy?", "agent-1", 512)
    messages = mock_client.chat.completions.create.await_args.kwargs["messages"]
    assert "Use private deployment docs" in messages[0]["content"]


async def test_run_stream_omits_empty_long_term_context(mock_client, monkeypatch):
    from fleetent.intelligence.long_term_ctx import BuiltContext

    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok"))
    build_context = AsyncMock(return_value=BuiltContext(text="", sources=[]))
    monkeypatch.setattr(al, "build_context", build_context)

    [_ async for _ in al.run_stream("say hello")]

    messages = mock_client.chat.completions.create.await_args.kwargs["messages"]
    assert "[Long-term context]" not in messages[0]["content"]


def test_run_sync_calls_long_term_context(mock_client, monkeypatch):
    from fleetent.intelligence.long_term_ctx import BuiltContext

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    build_context = AsyncMock(return_value=BuiltContext(text="CLI memory", sources=[]))
    monkeypatch.setattr(al, "build_context", build_context)
    monkeypatch.setattr(al, "scan_skills", lambda: None)

    result = al.run_sync("hello", user_id="user-1")

    assert result == "ok"
    build_context.assert_awaited_once_with("user-1", "hello", "", 512)
    messages = mock_client.chat.completions.create.await_args.kwargs["messages"]
    assert "CLI memory" in messages[0]["content"]


async def test_run_sub_agent_tool_intercepted_and_executed(mock_client):
    """sub_agent tool call is intercepted by agent_loop, not passed to dispatch."""
    from fleetent.sub_agent import SubAgentResult

    tasks_json = '[{"name": "t1", "prompt": "do it"}]'
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[
            _tool_resp(
                "sub_agent", f'{{"tasks": "{tasks_json.replace(chr(34), chr(92) + chr(34))}"}}'
            ),
            _text_resp("all done"),
        ]
    )

    fake_results = [
        SubAgentResult(name="t1", result="task result", error=None, parent_session_id="")
    ]

    with patch.object(al, "SubAgentExecutor") as mock_executor_cls:
        mock_instance = AsyncMock()
        mock_instance.run = AsyncMock(return_value=fake_results)
        mock_executor_cls.return_value = mock_instance

        result = await al.run([{"role": "user", "content": "run tasks"}])

    assert result == "all done"
    mock_instance.run.assert_called_once()
    call_kwargs = mock_instance.run.call_args[1]
    assert call_kwargs["parent_user_id"] == "default"


async def test_run_sub_agent_result_formatted_in_tool_message(mock_client):
    """Sub-agent results are formatted as [name] result lines in the tool message."""
    import json as _json

    from fleetent.sub_agent import SubAgentResult

    tasks = [{"name": "fetch", "prompt": "get data"}]
    args_json = _json.dumps({"tasks": _json.dumps(tasks)})

    mock_client.chat.completions.create = AsyncMock(
        side_effect=[_tool_resp("sub_agent", args_json), _text_resp("done")]
    )

    fake_results = [
        SubAgentResult(name="fetch", result="some data", error=None, parent_session_id=""),
    ]

    captured_messages: list = []

    async def capture_create(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        if len(captured_messages) < 4:
            return _tool_resp("sub_agent", args_json)
        return _text_resp("done")

    mock_client.chat.completions.create = AsyncMock(
        side_effect=[_tool_resp("sub_agent", args_json), _text_resp("done")]
    )

    with patch.object(al, "SubAgentExecutor") as mock_cls:
        inst = AsyncMock()
        inst.run = AsyncMock(return_value=fake_results)
        mock_cls.return_value = inst

        await al.run([{"role": "user", "content": "go"}], user_id="u1")

    # The tool result message passed to second LLM call contains formatted output
    call_messages = mock_client.chat.completions.create.call_args_list[1][1]["messages"]
    tool_msg = next(m for m in call_messages if m.get("role") == "tool")
    assert "[fetch] some data" in tool_msg["content"]


async def test_run_allowed_tools_filters_schemas(mock_client, monkeypatch):
    """allowed_tools restricts which tool schemas are sent to the LLM."""
    all_schemas = [
        {"type": "function", "function": {"name": "shell", "description": ""}},
        {"type": "function", "function": {"name": "calculate", "description": ""}},
        {"type": "function", "function": {"name": "get_current_time", "description": ""}},
    ]
    monkeypatch.setattr(al, "get_schemas", lambda: all_schemas)
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))

    await al.run(
        [{"role": "user", "content": "hi"}],
        allowed_tools=["calculate", "get_current_time"],
    )

    sent_tools = mock_client.chat.completions.create.call_args[1]["tools"]
    sent_names = [s["function"]["name"] for s in sent_tools]
    assert "shell" not in sent_names
    assert "calculate" in sent_names
    assert "get_current_time" in sent_names


async def test_run_allowed_tools_supports_wildcard(mock_client, monkeypatch):
    """allowed_tools patterns support fnmatch wildcards."""
    all_schemas = [
        {"type": "function", "function": {"name": "filesystem__read_file", "description": ""}},
        {"type": "function", "function": {"name": "filesystem__write_file", "description": ""}},
        {"type": "function", "function": {"name": "shell", "description": ""}},
    ]
    monkeypatch.setattr(al, "get_schemas", lambda: all_schemas)
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))

    await al.run(
        [{"role": "user", "content": "hi"}],
        allowed_tools=["filesystem__*"],
    )

    sent_tools = mock_client.chat.completions.create.call_args[1]["tools"]
    sent_names = [s["function"]["name"] for s in sent_tools]
    assert sent_names == ["filesystem__read_file", "filesystem__write_file"]


# ── fallback helpers ──────────────────────────────────────────────────────────


def _mk_http_error(status: int, cls=APIStatusError) -> APIStatusError:
    r = MagicMock()
    r.status_code = status
    r.request = MagicMock()
    r.headers = {}
    if cls is RateLimitError:
        return RateLimitError("rate limit", response=r, body={})
    return APIStatusError(f"status {status}", response=r, body={})


@pytest.fixture
def mock_client_fb(monkeypatch) -> AsyncMock:
    """mock_client variant with one fallback model configured."""
    from fleetent.intelligence.long_term_ctx import BuiltContext

    client = AsyncMock()
    cfg = RouteConfig(
        base_url="https://api.test.com",
        model="primary-model",
        api_key_env="TEST_KEY",
        max_tokens=512,
        fallbacks=("fallback-model",),
    )
    monkeypatch.setenv("TEST_KEY", "k")
    monkeypatch.setattr(al, "get_async_client_and_config", lambda _: (client, cfg))
    monkeypatch.setattr(al, "get_schemas", lambda: [])
    monkeypatch.setattr(al, "maybe_compress", lambda msgs: msgs)
    monkeypatch.setattr(al, "record_trace_event", lambda event: None)
    monkeypatch.setattr(al, "dispatch", lambda name, args, **kw: f"{name}_result")
    monkeypatch.setattr(al, "match_skill", lambda _: None)
    monkeypatch.setattr(
        al, "build_context", AsyncMock(return_value=BuiltContext(text="", sources=[]))
    )
    return client


# ── run() fallback ────────────────────────────────────────────────────────────


async def test_run_falls_back_on_429(mock_client_fb):
    mock_client_fb.chat.completions.create = AsyncMock(
        side_effect=[_mk_http_error(429, RateLimitError), _text_resp("fallback reply")]
    )
    result = await al.run([{"role": "user", "content": "hi"}])
    assert result == "fallback reply"
    calls = mock_client_fb.chat.completions.create.call_args_list
    assert calls[0].kwargs["model"] == "primary-model"
    assert calls[1].kwargs["model"] == "fallback-model"


async def test_run_falls_back_on_503(mock_client_fb):
    mock_client_fb.chat.completions.create = AsyncMock(
        side_effect=[_mk_http_error(503), _text_resp("ok")]
    )
    result = await al.run([{"role": "user", "content": "hi"}])
    assert result == "ok"


async def test_run_exhausted_fallbacks_raises(mock_client_fb):
    mock_client_fb.chat.completions.create = AsyncMock(
        side_effect=[_mk_http_error(429, RateLimitError), _mk_http_error(429, RateLimitError)]
    )
    with pytest.raises(RateLimitError):
        await al.run([{"role": "user", "content": "hi"}])


async def test_run_401_not_retried(mock_client_fb):
    mock_client_fb.chat.completions.create = AsyncMock(side_effect=_mk_http_error(401))
    with pytest.raises(APIStatusError) as exc_info:
        await al.run([{"role": "user", "content": "hi"}])
    assert exc_info.value.status_code == 401
    assert mock_client_fb.chat.completions.create.call_count == 1


# ── run_stream() fallback ─────────────────────────────────────────────────────


async def test_run_stream_falls_back_on_429(mock_client_fb):
    mock_client_fb.chat.completions.create = AsyncMock(
        side_effect=[_mk_http_error(429, RateLimitError), _stream_chunks("streamed", finish="stop")]
    )
    events = [e async for e in al.run_stream("hi")]
    text = "".join(e["content"] for e in events if e["type"] == "text_delta")
    assert "streamed" in text
    calls = mock_client_fb.chat.completions.create.call_args_list
    assert calls[1].kwargs["model"] == "fallback-model"


async def test_run_stream_exhausted_yields_error(mock_client_fb):
    mock_client_fb.chat.completions.create = AsyncMock(
        side_effect=[_mk_http_error(429, RateLimitError), _mk_http_error(429, RateLimitError)]
    )
    events = [e async for e in al.run_stream("hi")]
    assert any(e["type"] == "error" for e in events)


# ── agent trace fields: user_id, agent_name, streaming usage ─────────────────


async def test_run_records_agent_run_completed_trace_with_user_id(mock_client, monkeypatch):
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    captured: dict = {}
    monkeypatch.setattr(al, "record_trace_event", lambda event: captured.update(event=event))
    await al.run([{"role": "user", "content": "hi"}], user_id="user-99")
    event = captured["event"]
    assert event.event_type == "agent_run_completed"
    assert event.user_id == "user-99"
    assert event.payload["input"] == "hi"
    assert event.payload["reply"] == "ok"


async def test_run_records_agent_name_in_completed_trace(mock_client, monkeypatch):
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    captured: dict = {}
    monkeypatch.setattr(al, "record_trace_event", lambda event: captured.update(event=event))
    await al.run([{"role": "user", "content": "hi"}], agent_name="support-bot")
    event = captured["event"]
    assert event.agent_id == "support-bot"
    assert event.payload["agent_name"] == "support-bot"


async def test_run_stream_records_user_id_and_agent_name_in_completed_trace(
    mock_client, monkeypatch
):
    mock_client.chat.completions.create = AsyncMock(
        return_value=_stream_chunks("hi", finish="stop")
    )
    captured: dict = {}
    monkeypatch.setattr(al, "record_trace_event", lambda event: captured.update(event=event))
    [_ async for _ in al.run_stream("hi", user_id="user-7", agent_name="myagent")]
    event = captured["event"]
    assert event.event_type == "agent_run_completed"
    assert event.user_id == "user-7"
    assert event.agent_id == "myagent"
    assert event.payload["agent_name"] == "myagent"


async def test_run_stream_captures_usage_from_stream(mock_client, monkeypatch):
    mock_client.chat.completions.create = AsyncMock(
        return_value=_stream_chunks_with_usage(100, 50, "hello")
    )
    captured: dict = {}
    monkeypatch.setattr(al, "record_trace_event", lambda event: captured.update(event=event))
    [_ async for _ in al.run_stream("hi")]
    usage = captured["event"].payload["tokens"]
    assert usage == {"prompt": 100, "completion": 50, "total": 150}


async def test_agent_run_does_not_create_jsonl_trace_file(mock_client, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))

    await al.run([{"role": "user", "content": "hi"}])

    assert not (tmp_path / "data" / "traces.jsonl").exists()
