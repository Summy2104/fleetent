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
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **k: "")
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
    assert any(isinstance(m, dict) and m.get("role") == "assistant" for m in history), (
        "run() must append the assistant turn to the caller's messages list in place"
    )


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
    # AR2: the step dimension now flows through the budget; reaching max_turns stops
    # with budget_exceeded and a Grace Call (one extra LLM call) instead of a hard
    # cut. The LLM keeps requesting tools; the loop runs 2 turns then the grace call.
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[_tool_resp("get_time"), _tool_resp("get_time"), _text_resp("summary")]
    )
    result = await al.run([{"role": "user", "content": "go"}], max_turns=2)
    # 2 main turns + 1 grace call
    assert mock_client.chat.completions.create.call_count == 3
    assert result == "summary"


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


def test_build_controller_empty_history_yields_only_active_reasons():
    # With no tool history the loop-detection checker stays silent, so even with
    # every state flag tripped only active reasons can fire (priority unchanged).
    # AR2: the step dimension is now carried by the budget checker, so the step
    # limit surfaces as budget_exceeded rather than max_turns.
    from fleetent.budget import BudgetConfig, BudgetUsage

    config = BudgetConfig(max_turns=1, max_tokens=-1, max_cost_usd=-1.0)
    usage = BudgetUsage(turns=99)
    controller, _, _ = al._build_controller(
        1,
        1,
        include_approval=True,
        budget_config=config,
        budget_usage=usage,
        loop_repeat_threshold=3,
    )
    reason = controller.should_stop(
        LoopState(turn=99, consecutive_failures=99, approval_rejected=True)
    )
    assert reason in {
        StopReason.budget_exceeded,
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


async def test_run_logs_stop_reason_budget_exceeded_on_turns(mock_client):
    # AR2: the step dimension now logs budget_exceeded + budget_dimension="turns"
    # (max_turns is retired from the loop's produced reasons). A Grace Call follows.
    captured: dict = {}
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[_tool_resp("t"), _text_resp("summary")]
    )
    with patch.object(al, "log_run", lambda *a, **kw: captured.update(kw)):
        await al.run([{"role": "user", "content": "x"}], max_turns=1)
    assert captured.get("stop_reason") == StopReason.budget_exceeded
    assert captured.get("budget_dimension") == "turns"


async def test_run_stream_logs_stop_reason_budget_exceeded_on_turns(mock_client):
    captured: dict = {}
    streams = [_looping_tool_stream(), _text_stream("summary")]
    mock_client.chat.completions.create = AsyncMock(side_effect=lambda *a, **k: streams.pop(0))
    with patch.object(al, "log_run", lambda *a, **kw: captured.update(kw)):
        _ = [e async for e in al.run_stream("go", max_turns=1)]
    assert captured.get("stop_reason") == StopReason.budget_exceeded
    assert captured.get("budget_dimension") == "turns"


# ── cancellation (AR19) ────────────────────────────────────────────────────


async def test_run_cancelled_stops_before_llm_call(mock_client):
    from fleetent.cancellation import CancelToken

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("hi"))
    token = CancelToken()
    token.cancel()
    reply = await al.run([{"role": "user", "content": "x"}], cancel_token=token)
    assert reply == ""
    # Checkpoint hit before the first LLM call: the model is never invoked.
    assert mock_client.chat.completions.create.call_count == 0


async def test_run_cancelled_logs_stop_reason_cancelled(mock_client):
    from fleetent.cancellation import CancelToken

    captured: dict = {}
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("hi"))
    token = CancelToken()
    token.cancel()
    with patch.object(al, "log_run", lambda *a, **kw: captured.update(kw)):
        await al.run([{"role": "user", "content": "x"}], cancel_token=token)
    assert captured.get("stop_reason") == StopReason.cancelled


async def test_run_default_no_token_behaves_normally(mock_client):
    # Not passing a token must leave behavior byte-identical to the status quo.
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("hello"))
    reply = await al.run([{"role": "user", "content": "x"}])
    assert reply == "hello"
    assert mock_client.chat.completions.create.call_count == 1


async def test_run_threads_token_to_dispatch(mock_client):
    from fleetent.cancellation import CancelToken

    seen: dict = {}

    def _capture_dispatch(name, args, **kw):
        seen["cancel_token"] = kw.get("cancel_token")
        return f"{name}_result"

    mock_client.chat.completions.create = AsyncMock(
        side_effect=[_tool_resp("get_time"), _text_resp("done")]
    )
    token = CancelToken()
    with patch.object(al, "dispatch", _capture_dispatch):
        await al.run([{"role": "user", "content": "x"}], cancel_token=token)
    assert seen["cancel_token"] is token


async def test_run_stream_cancelled_stops_before_llm_and_finishes_clean(mock_client):
    from fleetent.cancellation import CancelToken

    mock_client.chat.completions.create = AsyncMock(
        side_effect=lambda *a, **k: _looping_tool_stream()
    )
    token = CancelToken()
    token.cancel()
    events = [e async for e in al.run_stream("go", cancel_token=token)]
    assert mock_client.chat.completions.create.call_count == 0
    # Cancellation hits the checkpoint and the stream still closes via `done`.
    assert events[-1]["type"] == "done"


async def test_run_stream_cancelled_logs_stop_reason(mock_client):
    from fleetent.cancellation import CancelToken

    captured: dict = {}
    mock_client.chat.completions.create = AsyncMock(
        side_effect=lambda *a, **k: _looping_tool_stream()
    )
    token = CancelToken()
    token.cancel()
    with patch.object(al, "log_run", lambda *a, **kw: captured.update(kw)):
        _ = [e async for e in al.run_stream("go", cancel_token=token)]
    assert captured.get("stop_reason") == StopReason.cancelled


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
    # AR2: step limit → budget_exceeded + streaming Grace Call (one extra LLM call).
    streams = [_looping_tool_stream(), _looping_tool_stream(), _text_stream("summary")]
    mock_client.chat.completions.create = AsyncMock(side_effect=lambda *a, **k: streams.pop(0))
    events = [e async for e in al.run_stream("go", max_turns=2)]
    # 2 main turns + 1 grace call
    assert mock_client.chat.completions.create.call_count == 3
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
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **k: "")
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


async def test_run_forwards_disabled_skills_trace_to_log_run(mock_client, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    trace = [{"name": "off", "reason": "frontmatter_disabled"}]
    await al.run([{"role": "user", "content": "hi"}], disabled_skills_trace=trace)
    assert captured.get("disabled_skills_trace") == trace


async def test_run_no_disabled_skills_trace_when_none(mock_client, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    await al.run([{"role": "user", "content": "hi"}])
    assert captured.get("disabled_skills_trace") is None


def test_run_sync_collects_disabled_skills_trace(monkeypatch):
    captured: dict = {}

    async def fake_run(messages, **kw):
        captured.update(kw)
        return "done"

    monkeypatch.setattr(al, "scan_skills", lambda *a, **kw: None)
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **kw: "")
    monkeypatch.setattr(al, "load_memories", lambda **kw: "")
    monkeypatch.setattr(al, "run", fake_run)
    trace = [{"name": "off", "reason": "frontmatter_disabled"}]
    monkeypatch.setattr(al, "collect_disabled_trace", lambda *a, **kw: trace)
    al.run_sync("hi")
    assert captured.get("disabled_skills_trace") == trace


async def test_run_stream_logs_disabled_skills_trace(mock_client, monkeypatch):
    captured: dict = {}
    trace = [{"name": "off", "reason": "config_disabled"}]
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    monkeypatch.setattr(al, "collect_disabled_trace", lambda *a, **kw: trace)
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **kw: "")
    monkeypatch.setattr(al, "load_memories", lambda **kw: "")
    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok"))
    _ = [e async for e in al.run_stream("hi")]
    assert captured.get("disabled_skills_trace") == trace


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


# ── run() multimodal (AR21) ─────────────────────────────────────────────────────

_IMG_BLOCK = {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}}


async def test_run_passes_image_blocks_through_to_llm(mock_client):
    captured: dict = {}

    async def capture_create(*a, **kw):
        captured["messages"] = kw["messages"]
        return _text_resp("ok")

    mock_client.chat.completions.create = capture_create
    msg_content = [{"type": "text", "text": "what is this"}, _IMG_BLOCK]
    await al.run([{"role": "user", "content": msg_content}])
    sent = captured["messages"]
    user_msg = next(m for m in sent if m.get("role") == "user")
    assert isinstance(user_msg["content"], list)
    assert any(b.get("type") == "image_url" for b in user_msg["content"])


async def test_run_extracts_text_block_as_user_input(mock_client, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        al, "log_run", lambda user_input, *a, **kw: captured.__setitem__("input", user_input)
    )
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    content = [{"type": "text", "text": "describe the screenshot"}, _IMG_BLOCK]
    await al.run([{"role": "user", "content": content}])
    assert captured["input"] == "describe the screenshot"


async def test_run_str_content_regression(mock_client):
    # Plain-text path must be unchanged: no image block, default route.
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("plain"))
    result = await al.run([{"role": "user", "content": "just text"}])
    assert result == "plain"


async def test_run_routes_to_vision_when_image_present(monkeypatch):
    seen: list[str] = []
    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "vision-model"
    cfg.max_tokens = 512
    cfg.fallbacks = ()
    client.chat.completions.create = AsyncMock(return_value=_text_resp("seen"))

    def spy(task_type):
        seen.append(task_type)
        return client, cfg

    monkeypatch.setattr(al, "get_async_client_and_config", spy)
    monkeypatch.setattr(al, "get_schemas", lambda: [])
    monkeypatch.setattr(al, "maybe_compress", lambda msgs: msgs)
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(al, "extract_and_save", lambda *a, **kw: None)
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (50, 3),
    )
    await al.run([{"role": "user", "content": [{"type": "text", "text": "x"}, _IMG_BLOCK]}])
    assert "vision" in seen
    assert "default" not in seen


async def test_run_uses_default_route_for_text(mock_client, monkeypatch):
    seen: list[str] = []
    client = mock_client
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512
    cfg.fallbacks = ()

    def spy(t):
        seen.append(t)
        return client, cfg

    monkeypatch.setattr(al, "get_async_client_and_config", spy)
    client.chat.completions.create = AsyncMock(return_value=_text_resp("t"))
    await al.run([{"role": "user", "content": "hello"}])
    assert seen == ["default"]


async def test_run_raises_when_image_but_no_vision_route(mock_client, monkeypatch):
    from fleetent import model_router

    routes_no_vision = {k: v for k, v in model_router.ROUTES.items() if k != "vision"}
    monkeypatch.setattr(model_router, "ROUTES", routes_no_vision)
    create = AsyncMock(return_value=_text_resp("should not happen"))
    mock_client.chat.completions.create = create
    with pytest.raises(RuntimeError, match="vision|视觉"):
        await al.run([{"role": "user", "content": [_IMG_BLOCK]}])
    create.assert_not_called()


async def test_image_message_passes_sanitize(mock_client):
    # AR6 coordination: list-type content must survive sanitize() without error.
    from fleetent.message_hygiene import sanitize

    messages = [{"role": "user", "content": [{"type": "text", "text": "hi"}, _IMG_BLOCK]}]
    clean, report = sanitize(messages)
    assert clean[0]["content"] == messages[0]["content"]


# ── run_stream() multimodal (AR21) ──────────────────────────────────────────────


async def test_run_stream_passes_images_through(mock_client):
    captured: dict = {}

    async def capture_create(*a, **kw):
        captured["messages"] = kw["messages"]
        return _stream_chunks("ok", None)

    mock_client.chat.completions.create = capture_create
    events = [e async for e in al.run_stream("what is this", images=[(b"PNGDATA", "image/png")])]
    user_msg = next(m for m in captured["messages"] if m.get("role") == "user")
    assert isinstance(user_msg["content"], list)
    assert any(b.get("type") == "image_url" for b in user_msg["content"])
    assert any(e["type"] == "done" for e in events)


async def test_run_stream_text_path_unchanged(mock_client):
    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("hi", None))
    events = [e async for e in al.run_stream("plain text")]
    assert [e["content"] for e in events if e["type"] == "text_delta"] == ["hi"]


async def test_run_stream_routes_to_vision_with_images(monkeypatch):
    seen: list[str] = []
    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "vision-model"
    cfg.max_tokens = 512
    cfg.fallbacks = ()
    client.chat.completions.create = AsyncMock(return_value=_stream_chunks("x", None))

    def spy(t):
        seen.append(t)
        return client, cfg

    monkeypatch.setattr(al, "get_async_client_and_config", spy)
    monkeypatch.setattr(al, "get_schemas", lambda: [])
    monkeypatch.setattr(al, "maybe_compress", lambda msgs: msgs)
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(al, "extract_and_save", lambda *a, **kw: None)
    monkeypatch.setattr(al, "load_memories", lambda **kw: "")
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (50, 3),
    )
    _ = [e async for e in al.run_stream("desc", images=[(b"D", "image/png")])]
    assert "vision" in seen
    assert "default" not in seen


async def test_run_stream_raises_when_image_but_no_vision_route(mock_client, monkeypatch):
    from fleetent import model_router

    routes_no_vision = {k: v for k, v in model_router.ROUTES.items() if k != "vision"}
    monkeypatch.setattr(model_router, "ROUTES", routes_no_vision)
    create = MagicMock()
    mock_client.chat.completions.create = create
    with pytest.raises(RuntimeError, match="vision|视觉"):
        _ = [e async for e in al.run_stream("x", images=[(b"D", "image/png")])]
    create.assert_not_called()


# ── force_model / request-routing-override (MR1) ─────────────────────────────


def _route_spy(monkeypatch, calls: list[dict], fallbacks: tuple[str, ...] = ()):
    """Patch get_async_client_and_config with a spy recording (task_type, override).

    The returned cfg.model reflects override.model when set, mirroring the real
    router's _apply_override result so the loop's models_to_try uses it.
    """
    client = AsyncMock()

    def spy(task_type, override=None):
        cfg = MagicMock()
        cfg.model = override.model if override is not None and override.model else "test-model"
        cfg.max_tokens = 512
        cfg.fallbacks = () if (override is not None and override.model) else fallbacks
        calls.append({"task_type": task_type, "override": override})
        return client, cfg

    monkeypatch.setattr(al, "get_async_client_and_config", spy)
    return client


async def test_run_force_model_none_passes_no_override(mock_client, monkeypatch):
    calls: list[dict] = []
    client = _route_spy(monkeypatch, calls, fallbacks=("fb-1",))
    client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    await al.run([{"role": "user", "content": "hi"}], force_model=None)
    assert calls[0]["override"] is None


async def test_run_force_model_passes_override(mock_client, monkeypatch):
    from fleetent.model_router import RouteOverride

    calls: list[dict] = []
    client = _route_spy(monkeypatch, calls)
    client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    await al.run([{"role": "user", "content": "hi"}], force_model="claude-haiku-4-5")
    assert calls[0]["override"] == RouteOverride(model="claude-haiku-4-5")


async def test_run_force_model_used_for_every_llm_call(mock_client, monkeypatch):
    calls: list[dict] = []
    client = _route_spy(monkeypatch, calls, fallbacks=("fb-1",))
    # Two turns: tool call then final reply; both must use the forced model.
    client.chat.completions.create = AsyncMock(side_effect=[_tool_resp("echo"), _text_resp("done")])
    monkeypatch.setattr(al, "get_schemas", lambda: [])
    monkeypatch.setattr(al, "dispatch", lambda name, args, **kw: "r")
    await al.run([{"role": "user", "content": "hi"}], force_model="claude-haiku-4-5")
    create_calls = client.chat.completions.create.call_args_list
    assert all(c.kwargs["model"] == "claude-haiku-4-5" for c in create_calls)


async def test_run_force_model_trace_records_forced_model(mock_client, monkeypatch):
    calls: list[dict] = []
    client = _route_spy(monkeypatch, calls)
    client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    await al.run([{"role": "user", "content": "hi"}], force_model="claude-haiku-4-5")
    assert captured["model_used"] == "claude-haiku-4-5"


async def test_run_no_force_model_trace_records_default(mock_client, monkeypatch):
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    await al.run([{"role": "user", "content": "hi"}])
    assert captured["model_used"] == "test-model"


async def test_run_stream_force_model_none_passes_no_override(mock_client, monkeypatch):
    calls: list[dict] = []
    client = _route_spy(monkeypatch, calls, fallbacks=("fb-1",))
    client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok", finish="stop"))
    _ = [e async for e in al.run_stream("hi", force_model=None)]
    assert calls[0]["override"] is None


async def test_run_stream_force_model_passes_override(mock_client, monkeypatch):
    from fleetent.model_router import RouteOverride

    calls: list[dict] = []
    client = _route_spy(monkeypatch, calls)
    client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok", finish="stop"))
    _ = [e async for e in al.run_stream("hi", force_model="claude-haiku-4-5")]
    assert calls[0]["override"] == RouteOverride(model="claude-haiku-4-5")


async def test_run_stream_force_model_used_for_llm_call(mock_client, monkeypatch):
    calls: list[dict] = []
    client = _route_spy(monkeypatch, calls, fallbacks=("fb-1",))
    client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok", finish="stop"))
    _ = [e async for e in al.run_stream("hi", force_model="claude-haiku-4-5")]
    create_calls = client.chat.completions.create.call_args_list
    assert all(c.kwargs["model"] == "claude-haiku-4-5" for c in create_calls)


async def test_run_stream_force_model_trace_records_forced_model(mock_client, monkeypatch):
    calls: list[dict] = []
    client = _route_spy(monkeypatch, calls)
    client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok", finish="stop"))
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    _ = [e async for e in al.run_stream("hi", force_model="claude-haiku-4-5")]
    assert captured["model_used"] == "claude-haiku-4-5"


# ── provider health cache integration (MR3) ──────────────────────────────────


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _install_health_cache(monkeypatch, *, failure_threshold=1, cooldown_seconds=60, clock=None):
    import fleetent.provider_health as ph

    clock = clock or _FakeClock()
    cache = ph.ProviderHealthCache(
        failure_threshold=failure_threshold, cooldown_seconds=cooldown_seconds, now=clock
    )
    monkeypatch.setattr(ph, "_cache", cache)
    return cache, clock


async def test_call_records_failure_on_switchable_error(mock_client_fb, monkeypatch):
    cache, _ = _install_health_cache(monkeypatch, failure_threshold=3)
    mock_client_fb.chat.completions.create = AsyncMock(
        side_effect=[_mk_http_error(429, RateLimitError), _text_resp("ok")]
    )
    await al.run([{"role": "user", "content": "hi"}])
    assert cache._state("primary-model").consecutive_failures == 1


async def test_call_success_records_success(mock_client_fb, monkeypatch):
    cache, _ = _install_health_cache(monkeypatch, failure_threshold=3)
    cache.record_failure("primary-model")
    cache.record_failure("primary-model")
    mock_client_fb.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    await al.run([{"role": "user", "content": "hi"}])
    assert cache._state("primary-model").consecutive_failures == 0


async def test_call_skips_cooling_provider(mock_client_fb, monkeypatch):
    cache, _ = _install_health_cache(monkeypatch, failure_threshold=1, cooldown_seconds=60)
    cache.record_failure("primary-model")  # primary now in cooldown
    mock_client_fb.chat.completions.create = AsyncMock(return_value=_text_resp("from fb"))
    result = await al.run([{"role": "user", "content": "hi"}])
    assert result == "from fb"
    calls = mock_client_fb.chat.completions.create.call_args_list
    # primary skipped entirely; only the fallback model was called.
    assert all(c.kwargs["model"] == "fallback-model" for c in calls)


async def test_call_half_open_retries_after_cooldown(mock_client_fb, monkeypatch):
    cache, clock = _install_health_cache(monkeypatch, failure_threshold=1, cooldown_seconds=60)
    cache.record_failure("primary-model")
    clock.advance(60)  # cooldown elapsed → half-open
    mock_client_fb.chat.completions.create = AsyncMock(return_value=_text_resp("primary ok"))
    result = await al.run([{"role": "user", "content": "hi"}])
    assert result == "primary ok"
    calls = mock_client_fb.chat.completions.create.call_args_list
    assert calls[0].kwargs["model"] == "primary-model"


async def test_non_health_status_error_never_marks_unavailable(mock_client_fb, monkeypatch):
    # 401 → should_switch_model=False → must NOT count as a provider failure.
    cache, _ = _install_health_cache(monkeypatch, failure_threshold=1)
    mock_client_fb.chat.completions.create = AsyncMock(side_effect=_mk_http_error(401))
    with pytest.raises(APIStatusError):
        await al.run([{"role": "user", "content": "hi"}])
    assert cache._state("primary-model").consecutive_failures == 0
    assert cache.is_available("primary-model") is True


async def test_400_never_marks_unavailable(mock_client_fb, monkeypatch):
    cache, _ = _install_health_cache(monkeypatch, failure_threshold=1)
    mock_client_fb.chat.completions.create = AsyncMock(side_effect=_mk_http_error(400))
    with pytest.raises(APIStatusError):
        await al.run([{"role": "user", "content": "hi"}])
    assert cache.is_available("primary-model") is True


async def test_call_all_cooling_does_not_return_empty(mock_client_fb, monkeypatch):
    # Both candidates in cooldown; loop must not silently succeed with no call.
    cache, _ = _install_health_cache(monkeypatch, failure_threshold=1, cooldown_seconds=60)
    cache.record_failure("primary-model")
    cache.record_failure("fallback-model")
    mock_client_fb.chat.completions.create = AsyncMock(
        side_effect=[_mk_http_error(429, RateLimitError), _mk_http_error(429, RateLimitError)]
    )
    with pytest.raises(RateLimitError):
        await al.run([{"role": "user", "content": "hi"}])
    # Fell back to probing the cooling candidates rather than returning empty.
    assert mock_client_fb.chat.completions.create.call_count >= 1


# ── run_stream() provider health integration ─────────────────────────────────


async def test_stream_skips_cooling_provider(mock_client_fb, monkeypatch):
    cache, _ = _install_health_cache(monkeypatch, failure_threshold=1, cooldown_seconds=60)
    cache.record_failure("primary-model")
    mock_client_fb.chat.completions.create = AsyncMock(
        return_value=_stream_chunks("streamed", finish="stop")
    )
    events = [e async for e in al.run_stream("hi")]
    text = "".join(e["content"] for e in events if e["type"] == "text_delta")
    assert "streamed" in text
    calls = mock_client_fb.chat.completions.create.call_args_list
    assert all(c.kwargs["model"] == "fallback-model" for c in calls)


async def test_stream_records_success(mock_client_fb, monkeypatch):
    cache, _ = _install_health_cache(monkeypatch, failure_threshold=3)
    cache.record_failure("primary-model")
    mock_client_fb.chat.completions.create = AsyncMock(
        return_value=_stream_chunks("ok", finish="stop")
    )
    _ = [e async for e in al.run_stream("hi")]
    assert cache._state("primary-model").consecutive_failures == 0


async def test_stream_records_failure_on_switchable(mock_client_fb, monkeypatch):
    cache, _ = _install_health_cache(monkeypatch, failure_threshold=3)
    mock_client_fb.chat.completions.create = AsyncMock(
        side_effect=[_mk_http_error(429, RateLimitError), _stream_chunks("ok", finish="stop")]
    )
    _ = [e async for e in al.run_stream("hi")]
    assert cache._state("primary-model").consecutive_failures == 1


# ── sampling params pass-through (model-parameter-config) ─────────────────────


def _wire_loop(monkeypatch, client, cfg):
    """Wire a real RouteConfig (with params) through the loop, mocking the rest."""
    monkeypatch.setenv(cfg.api_key_env, "k")
    monkeypatch.setattr(al, "get_async_client_and_config", lambda _: (client, cfg))
    monkeypatch.setattr(al, "get_schemas", lambda: [])
    monkeypatch.setattr(al, "maybe_compress", lambda msgs: msgs)
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(al, "extract_and_save", lambda *a, **kw: None)
    monkeypatch.setattr(al, "dispatch", lambda name, args, **kw: f"{name}_result")
    monkeypatch.setattr(al, "load_memories", lambda **kw: "")
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns if max_turns is not None else 50,
            max_consecutive_failures if max_consecutive_failures is not None else 3,
        ),
    )


def _cfg_with_params(params: dict, fallbacks: tuple = ()) -> RouteConfig:
    return RouteConfig(
        base_url="https://api.test.com",
        model="primary-model",
        api_key_env="TEST_KEY",
        max_tokens=512,
        fallbacks=fallbacks,
        params=params,
    )


async def test_call_passes_params_alongside_max_tokens(monkeypatch):
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    _wire_loop(monkeypatch, client, _cfg_with_params({"temperature": 0.0, "top_p": 0.9}))
    await al.run([{"role": "user", "content": "hi"}])
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["temperature"] == 0.0
    assert kwargs["top_p"] == 0.9
    assert kwargs["max_tokens"] == 512


async def test_call_empty_params_sends_no_sampling_kwargs(monkeypatch):
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    _wire_loop(monkeypatch, client, _cfg_with_params({}))
    await al.run([{"role": "user", "content": "hi"}])
    kwargs = client.chat.completions.create.call_args.kwargs
    assert set(kwargs) == {"model", "messages", "tools", "max_tokens"}


async def test_stream_passes_params_alongside_max_tokens(monkeypatch):
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok", finish="stop"))
    _wire_loop(monkeypatch, client, _cfg_with_params({"temperature": 0.2}))
    _ = [e async for e in al.run_stream("hi")]
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["temperature"] == 0.2
    assert kwargs["max_tokens"] == 512
    assert kwargs["stream"] is True
    assert kwargs["stream_options"] == {"include_usage": True}


async def test_stream_empty_params_byte_identical(monkeypatch):
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok", finish="stop"))
    _wire_loop(monkeypatch, client, _cfg_with_params({}))
    _ = [e async for e in al.run_stream("hi")]
    kwargs = client.chat.completions.create.call_args.kwargs
    assert set(kwargs) == {
        "model",
        "messages",
        "tools",
        "max_tokens",
        "stream",
        "stream_options",
    }


# ── prompt-cache-optimization: stable cacheable prefix ───────────────────────


def _capture_stream_wire(monkeypatch, *, memory: str, catalog: str) -> dict:
    """Wire run_stream with a given memory ctx + skills catalog, capturing messages."""
    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512
    cfg.fallbacks = ()
    cfg.params = {}
    captured: dict = {}

    async def fake_create(*, model, messages, **kw):
        captured["messages"] = [dict(m) for m in messages]
        return _stream_chunks("ok", None)

    client.chat.completions.create = fake_create
    monkeypatch.setattr(al, "get_async_client_and_config", lambda _: (client, cfg))
    monkeypatch.setattr(al, "get_schemas", lambda: [])
    monkeypatch.setattr(al, "maybe_compress", lambda msgs: msgs)
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(al, "extract_and_save", lambda *a, **kw: None)
    monkeypatch.setattr(al, "load_memories", lambda **kw: memory)
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **kw: catalog)
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns if max_turns is not None else 50,
            max_consecutive_failures if max_consecutive_failures is not None else 3,
        ),
    )
    return captured


_BASE = "You are a helpful assistant with access to tools. Use them when needed."


async def test_run_stream_base_system_prefix_stable_across_variable_content(monkeypatch):
    # The skills catalog is part of the stable prefix; only memory varies. The
    # base system message (messages[0] = base + catalog) must be byte-identical
    # across runs so the auto prefix cache can hit.
    cap1 = _capture_stream_wire(monkeypatch, memory="mem-A", catalog="CATALOG-X")
    _ = [e async for e in al.run_stream("deploy please")]
    first = cap1["messages"][0]

    cap2 = _capture_stream_wire(monkeypatch, memory="mem-B-different", catalog="CATALOG-X")
    _ = [e async for e in al.run_stream("deploy please")]
    second = cap2["messages"][0]

    assert first["role"] == "system"
    assert first["content"] == f"{_BASE}\n\nCATALOG-X"
    assert second["content"] == first["content"]


async def test_run_stream_catalog_in_prefix_memory_after_base(monkeypatch):
    # The skills catalog rides in the stable prefix (messages[0]); the variable
    # memory is delivered after it, never inside messages[0].
    cap = _capture_stream_wire(monkeypatch, memory="REMEMBER-X", catalog="CATALOG-BODY")
    _ = [e async for e in al.run_stream("deploy please")]
    msgs = cap["messages"]
    assert "CATALOG-BODY" in msgs[0]["content"]
    assert "REMEMBER-X" not in msgs[0]["content"]
    assert any("REMEMBER-X" in str(m.get("content") or "") for m in msgs[1:])


async def test_run_stream_no_variable_content_is_single_base_system(monkeypatch):
    # No memory, no catalog → just the stable base system + user message.
    cap = _capture_stream_wire(monkeypatch, memory="", catalog="")
    _ = [e async for e in al.run_stream("hi")]
    msgs = cap["messages"]
    system_msgs = [m for m in msgs if m["role"] == "system"]
    assert len(system_msgs) == 1
    assert system_msgs[0]["content"] == _BASE


def test_run_sync_base_system_prefix_stable_across_variable_content(monkeypatch):
    captured: dict = {}

    async def fake_run(messages, **kw):
        captured.setdefault("runs", []).append([dict(m) for m in messages])
        return "done"

    monkeypatch.setattr(al, "scan_skills", lambda *a, **kw: None)
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **kw: "CATALOG-X")
    monkeypatch.setattr(al, "run", fake_run)

    monkeypatch.setattr(al, "load_memories", lambda **kw: "mem-A")
    al.run_sync("deploy please")

    monkeypatch.setattr(al, "load_memories", lambda **kw: "mem-B-bigger-different")
    al.run_sync("deploy please")

    run1, run2 = captured["runs"]
    assert run1[0]["role"] == "system"
    assert run1[0]["content"] == f"{_BASE}\n\nCATALOG-X"
    assert run2[0]["content"] == run1[0]["content"]
    # Memory still present, after the base+catalog prefix.
    full1 = "".join(str(m.get("content") or "") for m in run1)
    assert "mem-A" in full1
    assert "mem-A" not in run1[0]["content"]


# ── prompt-cache-optimization: cache metrics into trace ──────────────────────


async def test_run_logs_cache_tokens_from_usage(mock_client, monkeypatch):
    resp = _text_resp("ok")
    resp.usage.prompt_tokens = 200
    resp.usage.completion_tokens = 10
    resp.usage.total_tokens = 210
    resp.usage.cache_read_input_tokens = 150
    resp.usage.cache_creation_input_tokens = 50
    # Anthropic-style usage has no prompt_tokens_details.
    resp.usage.prompt_tokens_details = None
    mock_client.chat.completions.create = AsyncMock(return_value=resp)
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    await al.run([{"role": "user", "content": "hi"}])
    ct = captured.get("cache_tokens")
    assert ct is not None
    assert ct.get("cache_read_input_tokens") == 150
    assert ct.get("cache_creation_input_tokens") == 50


async def test_run_logs_openai_cached_tokens_from_usage(mock_client, monkeypatch):
    resp = _text_resp("ok")
    resp.usage.prompt_tokens = 200
    resp.usage.completion_tokens = 10
    resp.usage.total_tokens = 210
    # OpenAI-style nested cached_tokens; no Anthropic-style fields.
    del resp.usage.cache_read_input_tokens
    del resp.usage.cache_creation_input_tokens
    details = MagicMock()
    details.cached_tokens = 128
    resp.usage.prompt_tokens_details = details
    mock_client.chat.completions.create = AsyncMock(return_value=resp)
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    await al.run([{"role": "user", "content": "hi"}])
    ct = captured.get("cache_tokens")
    assert ct is not None
    assert ct.get("cached_tokens") == 128


async def _stream_chunks_with_cache_usage(*contents: str | None):
    async for chunk in _stream_chunks(*contents):
        yield chunk
    u = MagicMock()
    u.choices = []
    u.usage = MagicMock(
        spec=[
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        ]
    )
    u.usage.prompt_tokens = 300
    u.usage.completion_tokens = 20
    u.usage.total_tokens = 320
    u.usage.cache_read_input_tokens = 256
    u.usage.cache_creation_input_tokens = 44
    yield u


async def test_run_stream_logs_cache_tokens_from_usage_chunk(mock_client, monkeypatch):
    mock_client.chat.completions.create = AsyncMock(
        return_value=_stream_chunks_with_cache_usage("hello")
    )
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    [_ async for _ in al.run_stream("hi")]
    ct = captured.get("cache_tokens")
    assert ct is not None
    assert ct.get("cache_read_input_tokens") == 256
    assert ct.get("cache_creation_input_tokens") == 44


async def test_run_stream_no_cache_tokens_when_usage_lacks_fields(mock_client, monkeypatch):
    mock_client.chat.completions.create = AsyncMock(
        return_value=_stream_chunks_with_usage(100, 50, "hello")
    )
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    [_ async for _ in al.run_stream("hi")]
    assert captured.get("cache_tokens") is None


async def test_run_no_cache_tokens_when_usage_lacks_fields(mock_client, monkeypatch):
    resp = _text_resp("ok")
    resp.usage = MagicMock(spec=["prompt_tokens", "completion_tokens", "total_tokens"])
    resp.usage.prompt_tokens = 10
    resp.usage.completion_tokens = 5
    resp.usage.total_tokens = 15
    mock_client.chat.completions.create = AsyncMock(return_value=resp)
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))
    await al.run([{"role": "user", "content": "hi"}])
    assert captured.get("cache_tokens") is None


# ── prompt-cache-optimization: backend-agnostic guard (no cache_control) ─────


async def test_run_does_not_inject_cache_control_marker(mock_client):
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    await al.run([{"role": "user", "content": "hi"}])
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert "cache_control" not in kwargs
    serialized = repr(kwargs.get("messages"))
    assert "cache_control" not in serialized


# ── skill-hot-reload: in-flight request keeps its injected skill (task 5) ──────


async def test_run_stream_injected_skill_survives_concurrent_reload(
    mock_client, monkeypatch, tmp_path
):
    """A request that already injected the skill catalog is unaffected by a reload.

    The catalog is taken once at the start of run_stream and copied into the
    request's private system prompt; an atomic index swap mid-flight (D2/D4)
    cannot rewrite that already-built prompt.
    """
    import fleetent.skill_registry as sr

    skill_dir = tmp_path / "skills" / "deploy"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: deploy\ndescription: deploy code to servers.\n---\nDeploy it."
    )
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "_no_builtin")
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(tmp_path / "skills"))
    sr.scan()
    # Use the real catalog renderer (the fixture stubbed it out to "").
    monkeypatch.setattr(al, "available_skills_prompt", sr.available_skills_prompt)

    captured: dict = {}

    async def _capturing_create(*_a, **kwargs):
        captured["messages"] = kwargs["messages"]
        # Simulate a reload landing while this request is in flight.
        import shutil

        shutil.rmtree(skill_dir)
        sr.reload()
        return _stream_chunks("ok")

    mock_client.chat.completions.create = _capturing_create

    _ = [e async for e in al.run_stream("please deploy code to servers")]

    system_text = "\n".join(m["content"] for m in captured["messages"] if m.get("role") == "system")
    # Reload dropped the skill from the global index, but the in-flight request's
    # already-injected prompt still carries it.
    assert "<name>deploy</name>" in system_text
    assert sr.match("please deploy code to servers") is None


# ── loop detection (AR4) ─────────────────────────────────────────────────────


def _tool_resp_seq(name: str, args: str, n: int) -> list[MagicMock]:
    """n tool-call responses for `name`/`args` with unique call ids per turn."""
    return [_tool_resp(name, args=args, call_id=f"tc-{i}") for i in range(n)]


async def test_run_signal_a_warns_then_terminates(mock_client):
    # Same tool + same args repeatedly. threshold=2 → window 6.
    # turn1,2: warning requested (history 1,2 → 2 repeats) then injected.
    # turn3,4: repeat after warning injected → loop_detected.
    captured: dict = {}
    mock_client.chat.completions.create = AsyncMock(
        side_effect=_tool_resp_seq("read_file", '{"path": "a"}', 10)
    )
    with (
        patch.object(al, "dispatch", lambda name, args, **kw: "same result"),
        patch.object(al, "log_run", lambda *a, **kw: captured.update(kw)),
    ):
        result = await al.run(
            [{"role": "user", "content": "go"}],
            max_turns=50,
            loop_repeat_threshold=2,
        )
    assert captured.get("stop_reason") == StopReason.loop_detected
    assert result == ""
    # Force-stopped well before max_turns.
    assert mock_client.chat.completions.create.call_count < 10


async def test_run_signal_a_injects_user_warning(mock_client):
    captured: dict = {}
    mock_client.chat.completions.create = AsyncMock(
        side_effect=_tool_resp_seq("read_file", '{"path": "a"}', 10)
    )
    with (
        patch.object(al, "dispatch", lambda name, args, **kw: "same result"),
        patch.object(al, "log_run", lambda *a, **kw: captured.update({"messages": a[2]})),
    ):
        await al.run(
            [{"role": "user", "content": "go"}],
            max_turns=50,
            loop_repeat_threshold=2,
        )
    warnings = [
        m
        for m in captured["messages"]
        if isinstance(m, dict) and m.get("role") == "user" and "重复" in str(m.get("content", ""))
    ]
    assert warnings, "expected a user-role loop warning message injected into the history"


async def test_run_signal_b_warns_then_terminates(mock_client):
    # Same tool, DIFFERENT args each turn, but identical successful result.
    captured: dict = {}
    responses = [
        _tool_resp("search", args=f'{{"q": "term-{i}"}}', call_id=f"tc-{i}") for i in range(10)
    ]
    mock_client.chat.completions.create = AsyncMock(side_effect=responses)
    with (
        patch.object(al, "dispatch", lambda name, args, **kw: "identical stagnant result"),
        patch.object(al, "log_run", lambda *a, **kw: captured.update(kw)),
    ):
        await al.run(
            [{"role": "user", "content": "go"}],
            max_turns=50,
            loop_repeat_threshold=2,
        )
    assert captured.get("stop_reason") == StopReason.loop_detected


async def test_run_no_loop_when_args_and_results_vary(mock_client):
    # Different args AND different results each turn → never a loop; runs to a
    # final text reply normally.
    captured: dict = {}
    responses = [
        _tool_resp("search", args=f'{{"q": "term-{i}"}}', call_id=f"tc-{i}") for i in range(4)
    ] + [_text_resp("done")]
    mock_client.chat.completions.create = AsyncMock(side_effect=responses)
    calls = {"n": 0}

    def varying_dispatch(name: str, args: str, **kw) -> str:
        calls["n"] += 1
        return f"result-{calls['n']}"

    with (
        patch.object(al, "dispatch", varying_dispatch),
        patch.object(al, "log_run", lambda *a, **kw: captured.update(kw)),
    ):
        result = await al.run(
            [{"role": "user", "content": "go"}],
            max_turns=50,
            loop_repeat_threshold=2,
        )
    assert result == "done"
    assert captured.get("stop_reason") == StopReason.normal


async def test_run_stream_signal_a_terminates(mock_client):
    captured: dict = {}

    def looping_stream(*a, **k):
        async def _gen():
            c = MagicMock()
            c.usage = None
            c.choices = [MagicMock()]
            c.choices[0].delta.content = None
            tc_delta = MagicMock()
            tc_delta.index = 0
            tc_delta.id = "tc-x"
            tc_delta.function.name = "read_file"
            tc_delta.function.arguments = '{"path": "a"}'
            c.choices[0].delta.tool_calls = [tc_delta]
            c.choices[0].finish_reason = "tool_calls"
            yield c

        return _gen()

    mock_client.chat.completions.create = AsyncMock(side_effect=looping_stream)
    with (
        patch.object(al, "dispatch", lambda name, args, **kw: "same result"),
        patch.object(al, "log_run", lambda *a, **kw: captured.update(kw)),
    ):
        events = [e async for e in al.run_stream("go", max_turns=50, loop_repeat_threshold=2)]
    assert captured.get("stop_reason") == StopReason.loop_detected
    assert events[-1]["type"] == "done"
    # No extra event type is yielded for the injected warning.
    assert all(e["type"] in {"tool_call", "tool_result", "text_delta", "done"} for e in events)


async def test_run_warning_survives_same_round_compression(mock_client, monkeypatch):
    # D4b: the round that injects the warning also triggers maybe_compress. The
    # warning must still reach the next LLM call (not be swallowed by the summary).
    captured_messages: list = []

    def recording_compress(msgs):
        # Simulate a compression that drops everything but a system summary,
        # keeping only the leading system head — i.e. a destructive compaction.
        return [m for m in msgs if isinstance(m, dict) and m.get("role") == "system"][:1] or msgs

    # Capture the messages sent to the LLM on each call.
    orig_create = AsyncMock(side_effect=_tool_resp_seq("read_file", '{"path": "a"}', 10))

    async def capturing_create(**kwargs):
        captured_messages.append(list(kwargs.get("messages", [])))
        return await orig_create(**kwargs)

    mock_client.chat.completions.create = capturing_create
    monkeypatch.setattr(al, "maybe_compress", recording_compress)

    with patch.object(al, "dispatch", lambda name, args, **kw: "same result"):
        await al.run(
            [{"role": "user", "content": "go"}],
            max_turns=50,
            loop_repeat_threshold=2,
        )

    # Some LLM call after the warning was injected must include the warning text,
    # as a user-role message, despite the destructive same-round compression.
    found = any(
        any(
            isinstance(m, dict) and m.get("role") == "user" and "重复" in str(m.get("content", ""))
            for m in msgs
        )
        for msgs in captured_messages
    )
    assert found, "loop warning must remain visible to the LLM even when compression fires"


# ── AR2: three-dimensional budget + Grace Call ─────────────────────────────────


def _tool_resp_usage(prompt: int, completion: int, name: str = "loop_tool") -> MagicMock:
    """A tool-call response carrying real integer usage (for budget accumulation)."""
    resp = _tool_resp(name)
    resp.usage.prompt_tokens = prompt
    resp.usage.completion_tokens = completion
    resp.usage.total_tokens = prompt + completion
    return resp


def _text_resp_usage(text: str, prompt: int = 1, completion: int = 1) -> MagicMock:
    resp = _text_resp(text)
    resp.usage.prompt_tokens = prompt
    resp.usage.completion_tokens = completion
    resp.usage.total_tokens = prompt + completion
    return resp


async def test_run_accumulates_usage_each_turn_not_just_last(mock_client):
    # Three tool turns then text; the run accumulates per-turn rather than reading
    # only the final response.usage. Assert via the BudgetUsage handed to the loop.
    seen: dict = {}
    real_checker = al.BudgetChecker

    def spy_checker(config, usage):
        seen["usage"] = usage
        return real_checker(config, usage)

    mock_client.chat.completions.create = AsyncMock(
        side_effect=[
            _tool_resp_usage(10, 5),
            _tool_resp_usage(20, 7),
            _text_resp_usage("done", 30, 9),
        ]
    )
    with patch.object(al, "BudgetChecker", spy_checker):
        result = await al.run([{"role": "user", "content": "go"}])
    assert result == "done"
    # tokens = sum of all three turns, not just the last
    assert seen["usage"].tokens == (10 + 5) + (20 + 7) + (30 + 9)
    assert seen["usage"].turns == 3


async def test_run_compression_tokens_not_counted_in_budget(mock_client):
    # maybe_compress is mocked to a pass-through; its internal LLM (in context_mgr)
    # never flows through usage.add. Confirm only main-loop turns are counted.
    seen: dict = {}
    real_checker = al.BudgetChecker

    def spy_checker(config, usage):
        seen["usage"] = usage
        return real_checker(config, usage)

    compress_calls = {"n": 0}

    def counting_compress(msgs):
        compress_calls["n"] += 1
        return msgs

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp_usage("hi", 11, 3))
    with (
        patch.object(al, "BudgetChecker", spy_checker),
        patch.object(al, "maybe_compress", counting_compress),
    ):
        await al.run([{"role": "user", "content": "go"}])
    assert compress_calls["n"] >= 1
    # exactly one main-loop turn counted; compression added nothing
    assert seen["usage"].tokens == 11 + 3
    assert seen["usage"].turns == 1


async def test_run_token_budget_triggers_grace_call(mock_client):
    # Each turn burns 100 tokens; cap at 100 → exhausted after turn 1 → grace call.
    grace_text = "进展总结：已完成 X。"
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[
            _tool_resp_usage(60, 40),  # turn 1: 100 tokens → over cap
            _text_resp_usage(grace_text, 1, 1),  # grace call output
        ]
    )
    captured: dict = {}
    with patch.object(al, "log_run", lambda *a, **kw: captured.update(kw)):
        result = await al.run([{"role": "user", "content": "go"}], max_tokens=100)
    assert result == grace_text
    assert captured.get("stop_reason") == StopReason.budget_exceeded
    assert captured.get("budget_dimension") == "tokens"
    # one main turn + one grace call
    assert mock_client.chat.completions.create.call_count == 2


async def test_run_grace_call_uses_reserved_token_cap(mock_client):
    # The grace call must pass a reserved max_tokens (not the full cfg.max_tokens).
    grace_max = {"val": None}
    orig_create = AsyncMock(
        side_effect=[_tool_resp_usage(200, 0), _text_resp_usage("summary", 1, 1)]
    )

    async def capture_create(*a, **kw):
        # the second call is the grace call; capture its max_tokens
        if orig_create.await_count == 1:
            grace_max["val"] = kw.get("max_tokens")
        return await orig_create(*a, **kw)

    mock_client.chat.completions.create = capture_create
    await al.run([{"role": "user", "content": "go"}], max_tokens=100)
    assert grace_max["val"] == 512  # floor, since 100 * 0.05 < 512


async def test_run_grace_call_failure_returns_partial_result(mock_client):
    # Grace call raises → fall back to the last assistant text accumulated.
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[_tool_resp_usage(200, 0), RuntimeError("grace boom")]
    )
    captured: dict = {}
    with patch.object(al, "log_run", lambda *a, **kw: captured.update(kw)):
        result = await al.run([{"role": "user", "content": "go"}], max_tokens=100)
    # No assistant text was produced (only a tool call), so partial result is "".
    assert result == ""
    assert captured.get("stop_reason") == StopReason.budget_exceeded


async def test_run_turns_budget_produces_budget_exceeded_with_grace(mock_client):
    # Step dimension now flows through BudgetChecker → budget_exceeded + grace call,
    # not the retired max_turns hard cut.
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[_tool_resp_usage(1, 1), _tool_resp_usage(1, 1), _text_resp_usage("done", 1, 1)]
    )
    captured: dict = {}
    with patch.object(al, "log_run", lambda *a, **kw: captured.update(kw)):
        result = await al.run([{"role": "user", "content": "go"}], max_turns=2)
    assert captured.get("stop_reason") == StopReason.budget_exceeded
    assert captured.get("budget_dimension") == "turns"
    assert result == "done"  # grace summary, not a hard-cut empty


# ── AR2: run_stream budget + streaming Grace Call ──────────────────────────────


def _looping_tool_stream_usage(prompt: int, completion: int):
    """A streaming tool-call turn that also reports usage (for budget accrual)."""

    async def _gen():
        c = MagicMock()
        c.usage = None
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
        u = MagicMock()
        u.choices = []
        u.usage = MagicMock()
        u.usage.prompt_tokens = prompt
        u.usage.completion_tokens = completion
        u.usage.total_tokens = prompt + completion
        yield u

    return _gen()


def _text_stream(*parts: str):
    async def _gen():
        for i, p in enumerate(parts):
            c = MagicMock()
            c.usage = None
            c.choices = [MagicMock()]
            c.choices[0].delta.content = p
            c.choices[0].delta.tool_calls = None
            c.choices[0].finish_reason = "stop" if i == len(parts) - 1 else None
            yield c

    return _gen()


async def test_run_stream_accumulates_usage_each_turn(mock_client):
    seen: dict = {}
    real_checker = al.BudgetChecker

    def spy_checker(config, usage):
        seen["usage"] = usage
        return real_checker(config, usage)

    # two tool turns then a budget cap that is high enough not to trip until later;
    # we only assert per-turn accrual, so let it loop twice then finish.
    streams = [
        _looping_tool_stream_usage(10, 5),
        _looping_tool_stream_usage(20, 7),
        _text_stream("done"),
    ]
    mock_client.chat.completions.create = AsyncMock(side_effect=lambda *a, **k: streams.pop(0))
    with patch.object(al, "BudgetChecker", spy_checker):
        events = [e async for e in al.run_stream("go")]
    assert events[-1]["type"] == "done"
    assert seen["usage"].tokens == (10 + 5) + (20 + 7) + 0  # text turn had no usage chunk
    assert seen["usage"].turns == 3


async def test_run_stream_budget_triggers_streaming_grace_call(mock_client):
    # turn 1 burns 100 tokens (cap 100) → budget_exceeded → streaming grace call.
    streams = [
        _looping_tool_stream_usage(60, 40),
        _text_stream("总结：", "已完成 X。"),  # grace call streamed summary
    ]
    mock_client.chat.completions.create = AsyncMock(side_effect=lambda *a, **k: streams.pop(0))
    captured: dict = {}
    with patch.object(al, "log_run", lambda *a, **kw: captured.update(kw)):
        events = [e async for e in al.run_stream("go", max_tokens=100)]
    deltas = [e["content"] for e in events if e["type"] == "text_delta"]
    assert "".join(deltas) == "总结：已完成 X。"
    assert events[-1]["type"] == "done"
    assert captured.get("stop_reason") == StopReason.budget_exceeded
    assert captured.get("budget_dimension") == "tokens"


async def test_run_stream_grace_call_fails_before_any_delta(mock_client):
    # Grace call stream raises immediately → degrade to last accumulated text.
    call = {"n": 0}

    def side(*a, **k):
        call["n"] += 1
        if call["n"] == 1:
            return _looping_tool_stream_usage(200, 0)
        raise RuntimeError("grace stream boom")

    mock_client.chat.completions.create = AsyncMock(side_effect=side)
    events = [e async for e in al.run_stream("go", max_tokens=100)]
    # No prior assistant text → done with whatever partial (empty here), but stream
    # must still terminate cleanly with a done event.
    assert events[-1]["type"] == "done"


async def test_run_stream_grace_call_fails_after_partial_delta(mock_client):
    # Grace call yields one delta then errors mid-stream → keep what streamed, done.
    async def _partial_then_boom():
        c = MagicMock()
        c.usage = None
        c.choices = [MagicMock()]
        c.choices[0].delta.content = "部分总结"
        c.choices[0].delta.tool_calls = None
        c.choices[0].finish_reason = None
        yield c
        raise RuntimeError("mid-stream boom")

    streams = [_looping_tool_stream_usage(200, 0), _partial_then_boom()]
    mock_client.chat.completions.create = AsyncMock(side_effect=lambda *a, **k: streams.pop(0))
    events = [e async for e in al.run_stream("go", max_tokens=100)]
    deltas = [e["content"] for e in events if e["type"] == "text_delta"]
    assert "部分总结" in "".join(deltas)
    assert events[-1]["type"] == "done"


# ── SB3: code-execution schema filtering ─────────────────────────────────────


def _schema(name: str) -> dict:
    return {"type": "function", "function": {"name": name, "parameters": {}}}


def _tool_names_sent(client) -> set[str]:
    tools = client.chat.completions.create.call_args.kwargs["tools"]
    return {t["function"]["name"] for t in tools}


async def test_run_off_mode_excludes_run_code(mock_client, monkeypatch):
    from fleetent.sandbox_enablement import Mode

    monkeypatch.setattr(al, "get_schemas", lambda: [_schema("run_code"), _schema("calculate")])
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    await al.run([{"role": "user", "content": "hi"}], sandbox_mode=Mode.OFF)
    assert _tool_names_sent(mock_client) == {"calculate"}


async def test_run_selective_excludes_run_code_when_not_opted_in(mock_client, monkeypatch):
    from fleetent.sandbox_enablement import Mode

    monkeypatch.setattr(al, "get_schemas", lambda: [_schema("run_code"), _schema("calculate")])
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    await al.run(
        [{"role": "user", "content": "hi"}], sandbox_mode=Mode.SELECTIVE, agent_features={}
    )
    assert _tool_names_sent(mock_client) == {"calculate"}


async def test_run_selective_includes_run_code_when_opted_in(mock_client, monkeypatch):
    from fleetent.sandbox_enablement import Mode

    monkeypatch.setattr(al, "get_schemas", lambda: [_schema("run_code"), _schema("calculate")])
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    await al.run(
        [{"role": "user", "content": "hi"}],
        sandbox_mode=Mode.SELECTIVE,
        agent_features={"code_execution": True},
    )
    assert _tool_names_sent(mock_client) == {"run_code", "calculate"}


async def test_run_all_includes_run_code_when_unset(mock_client, monkeypatch):
    from fleetent.sandbox_enablement import Mode

    monkeypatch.setattr(al, "get_schemas", lambda: [_schema("run_code"), _schema("calculate")])
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    await al.run([{"role": "user", "content": "hi"}], sandbox_mode=Mode.ALL, agent_features={})
    assert _tool_names_sent(mock_client) == {"run_code", "calculate"}


async def test_run_all_excludes_run_code_when_explicit_false(mock_client, monkeypatch):
    from fleetent.sandbox_enablement import Mode

    monkeypatch.setattr(al, "get_schemas", lambda: [_schema("run_code"), _schema("calculate")])
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    await al.run(
        [{"role": "user", "content": "hi"}],
        sandbox_mode=Mode.ALL,
        agent_features={"code_execution": False},
    )
    assert _tool_names_sent(mock_client) == {"calculate"}


async def test_run_no_sandbox_mode_does_not_filter_run_code(mock_client, monkeypatch):
    # Backward compatible: callers that don't pass a mode keep run_code visible.
    monkeypatch.setattr(al, "get_schemas", lambda: [_schema("run_code"), _schema("calculate")])
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    await al.run([{"role": "user", "content": "hi"}])
    assert _tool_names_sent(mock_client) == {"run_code", "calculate"}


async def test_run_stream_off_mode_excludes_run_code(mock_client, monkeypatch):
    from fleetent.sandbox_enablement import Mode

    monkeypatch.setattr(al, "get_schemas", lambda: [_schema("run_code"), _schema("calculate")])
    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("done"))
    async for _ in al.run_stream("hi", sandbox_mode=Mode.OFF):
        pass
    assert _tool_names_sent(mock_client) == {"calculate"}


async def test_run_stream_all_includes_run_code(mock_client, monkeypatch):
    from fleetent.sandbox_enablement import Mode

    monkeypatch.setattr(al, "get_schemas", lambda: [_schema("run_code"), _schema("calculate")])
    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("done"))
    async for _ in al.run_stream("hi", sandbox_mode=Mode.ALL, agent_features={}):
        pass
    assert _tool_names_sent(mock_client) == {"run_code", "calculate"}


def test_run_sync_loads_plugins(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    import fleetent.plugin_loader as pl
    import fleetent.sandbox_enablement as se

    async def fake_run(messages, **kw):
        return "done"

    monkeypatch.setattr(al, "scan_skills", lambda *a, **kw: None)
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **kw: "")
    monkeypatch.setattr(al, "load_memories", lambda **kw: "")
    monkeypatch.setattr(al, "collect_disabled_trace", lambda *a, **kw: None)
    monkeypatch.setattr(al, "run", fake_run)
    monkeypatch.setattr(se, "get_effective_mode", AsyncMock(return_value=se.Mode.OFF))
    load_mock = MagicMock(return_value=[])
    monkeypatch.setattr(pl, "load_plugins", load_mock)
    al.run_sync("hi")
    load_mock.assert_called_once()


def test_run_sync_passes_effective_sandbox_mode(monkeypatch):
    from unittest.mock import AsyncMock

    import fleetent.sandbox_enablement as se

    captured: dict = {}

    async def fake_run(messages, **kw):
        captured.update(kw)
        return "done"

    monkeypatch.setattr(al, "scan_skills", lambda *a, **kw: None)
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **kw: "")
    monkeypatch.setattr(al, "load_memories", lambda **kw: "")
    monkeypatch.setattr(al, "collect_disabled_trace", lambda *a, **kw: None)
    monkeypatch.setattr(al, "run", fake_run)
    monkeypatch.setattr(se, "get_effective_mode", AsyncMock(return_value=se.Mode.OFF))
    al.run_sync("hi")
    assert captured.get("sandbox_mode") is se.Mode.OFF
