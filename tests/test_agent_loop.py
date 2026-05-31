"""Unit tests for agent_loop.run() and run_stream()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIStatusError, RateLimitError

import fleetent.agent_loop as al
from fleetent.model_router import RouteConfig
from fleetent.termination import LoopState, StopReason

# ── helpers ──────────────────────────────────────────────────────────────────


def _text_resp(text: str | None = "reply") -> MagicMock:
    msg = MagicMock()
    msg.content = text
    msg.tool_calls = None
    # model_dump() must yield a real dict: the loop appends it to messages and
    # the hygiene layer (AR6) operates on dict messages.
    msg.model_dump = lambda: {"role": "assistant", "content": text}

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
    msg.model_dump = lambda: {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": args}}
        ],
    }

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
    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512

    cfg.fallbacks = ()

    monkeypatch.setattr(al, "get_async_client_and_config", lambda _: (client, cfg))
    monkeypatch.setattr(al, "get_schemas", lambda: [])
    monkeypatch.setattr(al, "maybe_compress", lambda msgs: msgs)
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(al, "extract_and_save", lambda *a, **kw: None)
    monkeypatch.setattr(al, "dispatch", lambda name, args, **kw: f"{name}_result")
    monkeypatch.setattr(al, "load_memories", lambda **kw: "")
    monkeypatch.setattr(al, "match_skill", lambda _: None)
    # Avoid instantiating Settings() (needs an API key) in the default-limits path.
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns if max_turns is not None else 50,
            max_consecutive_failures if max_consecutive_failures is not None else 3,
        ),
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


async def test_run_mutates_caller_messages_in_place(mock_client):
    # im_gateway.normalizer passes `history` to run() then save()s it, relying on
    # run() appending the conversation in-place. sanitize/compress must not detach it.
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("hi there"))
    history: list = [{"role": "user", "content": "hi"}]
    await al.run(history)
    # the assistant reply must be present in the caller's own list (for session save)
    assert any(
        isinstance(m, dict) and m.get("role") == "assistant" for m in history
    ), "run() must append the assistant turn to the caller's messages list in place"


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


# ── run() termination ──────────────────────────────────────────────────────────


async def test_run_stops_at_max_turns(mock_client):
    # LLM keeps requesting tools forever; max_turns must break the loop.
    mock_client.chat.completions.create = AsyncMock(return_value=_tool_resp("get_time"))
    result = await al.run([{"role": "user", "content": "go"}], max_turns=2)
    assert mock_client.chat.completions.create.call_count == 2
    assert result == ""


async def test_run_stops_on_consecutive_failures(mock_client):
    mock_client.chat.completions.create = AsyncMock(return_value=_tool_resp("boom"))

    def failing_dispatch(name: str, args: str, **kw) -> str:
        raise RuntimeError("tool crashed")

    with patch.object(al, "dispatch", failing_dispatch):
        await al.run(
            [{"role": "user", "content": "go"}],
            max_consecutive_failures=2,
            max_turns=50,
        )
    assert mock_client.chat.completions.create.call_count == 2


async def test_run_success_resets_failure_count(mock_client):
    # fail, success, fail, then text — with threshold 2 the success reset prevents a stop.
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[_tool_resp("a"), _tool_resp("b"), _tool_resp("c"), _text_resp("done")]
    )
    calls = {"n": 0}

    def dispatch_seq(name: str, args: str, **kw) -> str:
        calls["n"] += 1
        if calls["n"] in (1, 3):
            raise RuntimeError("fail")
        return "ok"

    with patch.object(al, "dispatch", dispatch_seq):
        result = await al.run(
            [{"role": "user", "content": "go"}],
            max_consecutive_failures=2,
            max_turns=50,
        )
    assert result == "done"
    assert mock_client.chat.completions.create.call_count == 4


async def test_run_approval_rejected_terminates(mock_client, monkeypatch):
    mock_client.chat.completions.create = AsyncMock(return_value=_tool_resp("danger"))
    # The hygiene layer (AR6) returns a fresh list, so run() no longer mutates the
    # caller's input; inspect the messages handed to the trace instead.
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update({"messages": a[2]}))
    msgs = [{"role": "user", "content": "go"}]
    with (
        patch.object(al, "get_risk_level", lambda name: "high"),
        patch.object(al._default_gate, "request_approval", AsyncMock(return_value="rejected")),
    ):
        result = await al.run(msgs, reply_func=AsyncMock(), max_turns=50)
    # one LLM call, then terminated at next checkpoint — not a second call
    assert mock_client.chat.completions.create.call_count == 1
    assert result == ""
    # rejected tool still has a placeholder tool_result (message contract intact)
    assert any(isinstance(m, dict) and m.get("role") == "tool" for m in captured["messages"])


def test_build_controller_never_yields_reserved_reasons():
    # Reserved reasons (loop_detected/budget_exceeded/cancelled) have no checker,
    # so even with every state flag tripped only active reasons can fire.
    controller = al._build_controller(1, 1, include_approval=True)
    reason = controller.should_stop(
        LoopState(turn=99, consecutive_failures=99, approval_rejected=True)
    )
    assert reason in {
        StopReason.max_turns,
        StopReason.consecutive_failures,
        StopReason.approval_rejected,
    }


# ── stop_reason in trace ───────────────────────────────────────────────────────


async def test_run_logs_stop_reason_normal(mock_client):
    captured: dict = {}
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("hi"))
    with patch.object(al, "log_run", lambda *a, **kw: captured.update(kw)):
        await al.run([{"role": "user", "content": "x"}])
    assert captured.get("stop_reason") == StopReason.normal


async def test_run_logs_stop_reason_max_turns(mock_client):
    captured: dict = {}
    mock_client.chat.completions.create = AsyncMock(return_value=_tool_resp("t"))
    with patch.object(al, "log_run", lambda *a, **kw: captured.update(kw)):
        await al.run([{"role": "user", "content": "x"}], max_turns=1)
    assert captured.get("stop_reason") == StopReason.max_turns


async def test_run_stream_logs_stop_reason_max_turns(mock_client):
    captured: dict = {}
    mock_client.chat.completions.create = AsyncMock(
        side_effect=lambda *a, **k: _looping_tool_stream()
    )
    with patch.object(al, "log_run", lambda *a, **kw: captured.update(kw)):
        _ = [e async for e in al.run_stream("go", max_turns=1)]
    assert captured.get("stop_reason") == StopReason.max_turns


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


# ── run_stream() ──────────────────────────────────────────────────────────────


async def test_run_stream_yields_text_deltas_and_done(mock_client):
    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("hel", "lo", None))

    events = [e async for e in al.run_stream("say hello")]

    deltas = [e["content"] for e in events if e["type"] == "text_delta"]
    assert deltas == ["hel", "lo"]
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    assert done[0]["content"] == "hello"


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


def _looping_tool_stream():
    async def _gen():
        c = MagicMock()
        c.choices = [MagicMock()]
        c.choices[0].delta.content = None
        tc_delta = MagicMock()
        tc_delta.index = 0
        tc_delta.id = "tc-1"
        tc_delta.function.name = "loop_tool"
        tc_delta.function.arguments = "{}"
        c.choices[0].delta.tool_calls = [tc_delta]
        c.choices[0].finish_reason = "tool_calls"
        yield c

    return _gen()


async def test_run_stream_stops_at_max_turns(mock_client):
    mock_client.chat.completions.create = AsyncMock(
        side_effect=lambda *a, **k: _looping_tool_stream()
    )
    events = [e async for e in al.run_stream("go", max_turns=2)]
    assert mock_client.chat.completions.create.call_count == 2
    assert events[-1]["type"] == "done"


async def test_run_stream_stops_on_consecutive_failures(mock_client):
    mock_client.chat.completions.create = AsyncMock(
        side_effect=lambda *a, **k: _looping_tool_stream()
    )

    def failing_dispatch(name: str, args: str, **kw) -> str:
        raise RuntimeError("tool crashed")

    with patch.object(al, "dispatch", failing_dispatch):
        events = [e async for e in al.run_stream("go", max_consecutive_failures=2, max_turns=50)]
    assert mock_client.chat.completions.create.call_count == 2
    assert events[-1]["type"] == "done"


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
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(al, "extract_and_save", lambda *a, **kw: None)
    monkeypatch.setattr(al, "dispatch", lambda name, args, **kw: f"{name}_result")
    monkeypatch.setattr(al, "load_memories", lambda **kw: "")
    monkeypatch.setattr(al, "match_skill", lambda _: None)
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns if max_turns is not None else 50,
            max_consecutive_failures if max_consecutive_failures is not None else 3,
        ),
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


# ── log fields: user_id, agent_name, streaming usage ─────────────────────────


async def test_run_passes_user_id_to_log_run(mock_client, monkeypatch):
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    await al.run([{"role": "user", "content": "hi"}], user_id="user-99")
    assert captured.get("user_id") == "user-99"


async def test_run_passes_agent_name_to_log_run(mock_client, monkeypatch):
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    await al.run([{"role": "user", "content": "hi"}], agent_name="support-bot")
    assert captured.get("agent_name") == "support-bot"


async def test_run_stream_passes_user_id_and_agent_name_to_log_run(mock_client, monkeypatch):
    mock_client.chat.completions.create = AsyncMock(
        return_value=_stream_chunks("hi", finish="stop")
    )
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    [_ async for _ in al.run_stream("hi", user_id="user-7", agent_name="myagent")]
    assert captured.get("user_id") == "user-7"
    assert captured.get("agent_name") == "myagent"


async def test_run_stream_captures_usage_from_stream(mock_client, monkeypatch):
    mock_client.chat.completions.create = AsyncMock(
        return_value=_stream_chunks_with_usage(100, 50, "hello")
    )
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    [_ async for _ in al.run_stream("hi")]
    usage = captured.get("usage")
    assert usage is not None
    assert usage.prompt_tokens == 100
    assert usage.completion_tokens == 50


# ── classification-driven fallback + trace error_category ────────────────────


async def test_call_with_fallback_switches_on_classified_switchable(mock_client_fb):
    # 503 → classify → should_switch_model=True → try fallback model.
    mock_client_fb.chat.completions.create = AsyncMock(
        side_effect=[_mk_http_error(503), _text_resp("ok")]
    )
    result = await al.run([{"role": "user", "content": "hi"}])
    assert result == "ok"
    calls = mock_client_fb.chat.completions.create.call_args_list
    assert calls[1].kwargs["model"] == "fallback-model"


async def test_call_with_fallback_raises_on_non_switchable(mock_client_fb):
    # 403 → classify → should_switch_model=False → raise without trying fallback.
    mock_client_fb.chat.completions.create = AsyncMock(side_effect=_mk_http_error(403))
    with pytest.raises(APIStatusError) as exc_info:
        await al.run([{"role": "user", "content": "hi"}])
    assert exc_info.value.status_code == 403
    assert mock_client_fb.chat.completions.create.call_count == 1


async def test_run_logs_error_category_on_exhaustion(mock_client_fb, monkeypatch):
    mock_client_fb.chat.completions.create = AsyncMock(
        side_effect=[_mk_http_error(429, RateLimitError), _mk_http_error(429, RateLimitError)]
    )
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    with pytest.raises(RateLimitError):
        await al.run([{"role": "user", "content": "hi"}])
    assert captured.get("error_category") == "rate_limit"


async def test_run_no_error_category_on_success(mock_client, monkeypatch):
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    await al.run([{"role": "user", "content": "hi"}])
    assert captured.get("error_category") is None


async def test_run_stream_logs_error_category_on_exhaustion(mock_client_fb, monkeypatch):
    mock_client_fb.chat.completions.create = AsyncMock(
        side_effect=[_mk_http_error(429, RateLimitError), _mk_http_error(429, RateLimitError)]
    )
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    events = [e async for e in al.run_stream("hi")]
    assert any(e["type"] == "error" for e in events)
    assert captured.get("error_category") == "rate_limit"


# ── message hygiene integration (AR6) ───────────────────────────────────────


async def test_run_calls_sanitize_after_compress_before_llm(mock_client, monkeypatch):
    order: list[str] = []
    monkeypatch.setattr(al, "maybe_compress", lambda m: (order.append("compress"), m)[1])

    real_sanitize = al.sanitize

    def traced_sanitize(m):
        order.append("sanitize")
        return real_sanitize(m)

    monkeypatch.setattr(al, "sanitize", traced_sanitize)

    async def create(*a, **kw):
        order.append("llm")
        return _text_resp("hi")

    mock_client.chat.completions.create = AsyncMock(side_effect=create)
    await al.run([{"role": "user", "content": "hi"}])
    assert order[:3] == ["compress", "sanitize", "llm"]


async def test_run_sends_repaired_sequence_to_llm(mock_client):
    sent: dict = {}

    async def create(*a, **kw):
        sent["messages"] = kw["messages"]
        return _text_resp("ok")

    mock_client.chat.completions.create = AsyncMock(side_effect=create)
    # adjacent same-role user messages → must be merged before reaching the LLM
    await al.run(
        [
            {"role": "user", "content": "one"},
            {"role": "user", "content": "two"},
        ]
    )
    user_msgs = [m for m in sent["messages"] if m.get("role") == "user"]
    assert len(user_msgs) == 1


async def test_run_unrepairable_blocks_llm_call(mock_client, monkeypatch):
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("never"))
    # tool message missing tool_call_id → MessageContractError, no LLM call
    await al.run(
        [
            {"role": "user", "content": "hi"},
            {"role": "tool", "content": "broken"},
        ]
    )
    assert mock_client.chat.completions.create.call_count == 0


async def test_run_unrepairable_writes_error_trace(mock_client, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("x"))
    await al.run(
        [
            {"role": "user", "content": "hi"},
            {"role": "tool", "content": "broken"},
        ]
    )
    assert captured.get("error_category") == "unknown"


async def test_run_passes_hygiene_repairs_to_trace(mock_client, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    await al.run(
        [
            {"role": "user", "content": "one"},
            {"role": "user", "content": "two"},
        ]
    )
    assert captured.get("hygiene_repairs")
    assert "merged_same_role" in captured["hygiene_repairs"]


async def test_run_no_hygiene_repairs_when_clean(mock_client, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    await al.run([{"role": "user", "content": "hi"}])
    assert captured.get("hygiene_repairs") is None


async def test_run_stream_calls_sanitize_before_llm(mock_client, monkeypatch):
    order: list[str] = []
    real_sanitize = al.sanitize

    def traced_sanitize(m):
        order.append("sanitize")
        return real_sanitize(m)

    monkeypatch.setattr(al, "sanitize", traced_sanitize)

    async def create(*a, **kw):
        order.append("llm")
        return _stream_chunks("ok", None)

    mock_client.chat.completions.create = AsyncMock(side_effect=create)
    [e async for e in al.run_stream("hi")]
    assert order.index("sanitize") < order.index("llm")
