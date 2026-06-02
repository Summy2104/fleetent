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

    monkeypatch.setattr(al, "get_async_client_and_config", lambda *a, **k: (client, cfg))
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


async def test_run_records_agent_run_started_trace(mock_client, monkeypatch):
    from fleetent.observability import TraceEvent

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)

    await al.run(
        [{"role": "user", "content": "hi"}],
        user_id="user-1",
        agent_name="support-bot",
    )

    started = next(event for event in events if event.event_type == "agent_run_started")
    assert started.user_id == "user-1"
    assert started.agent_id == "support-bot"
    assert started.payload == {
        "user_id": "user-1",
        "agent_name": "support-bot",
        "entrypoint": "run",
    }


async def test_run_records_agent_run_failed_trace(mock_client, monkeypatch):
    from fleetent.observability import TraceEvent

    mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)

    with pytest.raises(RuntimeError):
        await al.run([{"role": "user", "content": "hi"}], user_id="user-1")

    failed = next(event for event in events if event.event_type == "agent_run_failed")
    assert failed.user_id == "user-1"
    assert failed.payload["entrypoint"] == "run"
    assert failed.payload["error_type"] == "RuntimeError"
    assert failed.payload["error_message"] == "boom"
    assert isinstance(failed.payload["elapsed_s"], float)


async def test_run_records_llm_call_started_and_completed(mock_client, monkeypatch):
    from fleetent.observability import TraceEvent

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)
    monkeypatch.setattr(
        al,
        "get_schemas",
        lambda: [
            {"type": "function", "function": {"name": "get_time"}},
            {"type": "function", "function": {"name": "calculate"}},
        ],
    )

    await al.run([{"role": "user", "content": "hi"}])

    started = next(event for event in events if event.event_type == "llm_call_started")
    completed = next(event for event in events if event.event_type == "llm_call_completed")
    assert started.payload == {
        "model": "test-model",
        "task_type": "default",
        "streaming": False,
        "message_count": 1,
        "tool_schema_count": 2,
    }
    assert completed.payload["model"] == "test-model"
    assert completed.payload["finish_reason"] == "stop"
    assert completed.payload["tokens"] == {
        "prompt": mock_client.chat.completions.create.return_value.usage.prompt_tokens,
        "completion": mock_client.chat.completions.create.return_value.usage.completion_tokens,
        "total": mock_client.chat.completions.create.return_value.usage.total_tokens,
    }
    assert isinstance(completed.payload["elapsed_s"], float)


async def test_run_records_llm_call_failed(mock_client, monkeypatch):
    from fleetent.observability import TraceEvent

    mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("provider down"))
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)

    with pytest.raises(RuntimeError):
        await al.run([{"role": "user", "content": "hi"}])

    failed = next(event for event in events if event.event_type == "llm_call_failed")
    assert failed.payload["model"] == "test-model"
    assert failed.payload["error_type"] == "RuntimeError"
    assert failed.payload["error_message"] == "provider down"
    assert isinstance(failed.payload["elapsed_s"], float)


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


async def test_run_records_tool_call_started_and_completed(mock_client, monkeypatch):
    from fleetent.observability import TraceEvent

    mock_client.chat.completions.create = AsyncMock(
        side_effect=[_tool_resp("get_time", '{"timezone":"UTC"}'), _text_resp("done")]
    )
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)
    monkeypatch.setattr(al, "get_risk_level", lambda name: "none")
    monkeypatch.setattr(al, "dispatch", lambda name, args, **kw: "tool result")

    await al.run([{"role": "user", "content": "what time?"}])

    started = next(event for event in events if event.event_type == "tool_call_started")
    completed = next(event for event in events if event.event_type == "tool_call_completed")
    assert started.payload["tool_name"] == "get_time"
    assert started.payload["tool_call_id"] == "tc-1"
    assert started.payload["risk_level"] == "none"
    assert started.payload["argument_summary"]["keys"] == ["timezone"]
    assert completed.payload["tool_name"] == "get_time"
    assert completed.payload["tool_call_id"] == "tc-1"
    assert completed.payload["result_summary"]["length"] == len("tool result")
    assert isinstance(completed.payload["elapsed_s"], float)


async def test_run_records_tool_call_failed(mock_client, monkeypatch):
    from fleetent.observability import TraceEvent

    mock_client.chat.completions.create = AsyncMock(side_effect=[_tool_resp("get_time")])
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)
    monkeypatch.setattr(al, "get_risk_level", lambda name: "none")

    def fail_dispatch(name: str, args: str, **kw) -> str:
        raise ValueError("bad tool")

    monkeypatch.setattr(al, "dispatch", fail_dispatch)

    with pytest.raises(ValueError):
        await al.run([{"role": "user", "content": "what time?"}])

    failed = next(event for event in events if event.event_type == "tool_call_failed")
    assert failed.payload["tool_name"] == "get_time"
    assert failed.payload["tool_call_id"] == "tc-1"
    assert failed.payload["error_type"] == "ValueError"
    assert failed.payload["error_message"] == "bad tool"
    assert isinstance(failed.payload["elapsed_s"], float)


async def test_run_records_permission_requested_and_resolved(mock_client, monkeypatch):
    from fleetent.observability import TraceEvent

    mock_client.chat.completions.create = AsyncMock(
        side_effect=[_tool_resp("write_file", '{"path":"x"}'), _text_resp("done")]
    )
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)
    monkeypatch.setattr(al, "get_risk_level", lambda name: "medium")
    monkeypatch.setattr(al, "dispatch", lambda name, args, **kw: "written")
    monkeypatch.setattr(
        al._default_gate,
        "request_approval",
        AsyncMock(return_value="approved"),
    )

    async def reply_func(message: str) -> None:
        return None

    await al.run([{"role": "user", "content": "write"}], user_id="user-1", reply_func=reply_func)

    requested = next(event for event in events if event.event_type == "permission_requested")
    resolved = next(event for event in events if event.event_type == "permission_resolved")
    assert requested.payload["tool_name"] == "write_file"
    assert requested.payload["risk_level"] == "medium"
    assert requested.payload["requester_user_id"] == "user-1"
    assert requested.payload["approval_id"]
    assert resolved.payload["approval_id"] == requested.payload["approval_id"]
    assert resolved.payload["decision"] == "approved"
    assert isinstance(resolved.payload["elapsed_s"], float)


async def test_run_records_context_compression_completed(mock_client, monkeypatch):
    from fleetent.observability import TraceEvent

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)

    def compress(messages):
        return [messages[0], messages[-1]]

    monkeypatch.setattr(al, "maybe_compress", compress)

    await al.run(
        [
            {"role": "system", "content": "sys"},
            {"role": "assistant", "content": "old"},
            {"role": "user", "content": "hi"},
        ]
    )

    compressed = next(
        event for event in events if event.event_type == "context_compression_completed"
    )
    assert compressed.payload["reason"] == "runtime_message_compression"
    assert compressed.payload["before_message_count"] == 3
    assert compressed.payload["after_message_count"] == 2
    assert isinstance(compressed.payload["elapsed_s"], float)


async def test_run_records_final_reply_emitted(mock_client, monkeypatch):
    from fleetent.observability import TraceEvent

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("final answer"))
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)

    await al.run([{"role": "user", "content": "hi"}])

    final = next(event for event in events if event.event_type == "final_reply_emitted")
    assert final.payload["reply_length"] == len("final answer")
    assert isinstance(final.payload["elapsed_s"], float)


async def test_run_runtime_events_share_run_id(mock_client, monkeypatch):
    from fleetent.observability import TraceEvent

    mock_client.chat.completions.create = AsyncMock(
        side_effect=[_tool_resp("get_time"), _text_resp("done")]
    )
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)
    monkeypatch.setattr(al, "get_risk_level", lambda name: "none")
    monkeypatch.setattr(al, "dispatch", lambda name, args, **kw: "tool result")

    await al.run([{"role": "user", "content": "what time?"}])

    runtime_events = [
        event
        for event in events
        if event.event_type
        in {
            "agent_run_started",
            "llm_call_started",
            "llm_call_completed",
            "tool_call_started",
            "tool_call_completed",
            "final_reply_emitted",
            "agent_run_completed",
        }
    ]
    assert len({event.run_id for event in runtime_events}) == 1


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
        memory_namespace="default",
    )
    messages = mock_client.chat.completions.create.await_args.kwargs["messages"]
    assert messages[0]["content"] == "base system\n\n[Long-term context]\nRemember user preference"


async def test_run_shares_run_id_between_injected_context_and_completion(mock_client, monkeypatch):
    from fleetent.intelligence.long_term_ctx import BuiltContext, ContextSource
    from fleetent.observability import TraceEvent

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    monkeypatch.setattr(
        al,
        "build_context",
        AsyncMock(
            return_value=BuiltContext(
                text="Remember user preference",
                sources=[
                    ContextSource(
                        source_type="memory",
                        source_id="memory-1",
                        score=0.91,
                        metadata={"type": "preference"},
                    )
                ],
            )
        ),
    )
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)

    def capture_injected_context(run_id, sources):
        events.append(
            TraceEvent(
                run_id=run_id,
                event_type="injected_context",
                payload={"sources": sources},
            )
        )

    monkeypatch.setattr(al, "record_injected_context", capture_injected_context)

    await al.run([{"role": "user", "content": "hi"}])

    injected = next(event for event in events if event.event_type == "injected_context")
    completed = next(event for event in events if event.event_type == "agent_run_completed")
    assert injected.run_id == completed.run_id


async def test_run_records_injected_context_sources(mock_client, monkeypatch):
    from fleetent.intelligence.long_term_ctx import BuiltContext, ContextSource

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    monkeypatch.setattr(
        al,
        "build_context",
        AsyncMock(
            return_value=BuiltContext(
                text="Use private deployment docs",
                sources=[
                    ContextSource(
                        source_type="knowledge",
                        source_id="chunk-1",
                        score=0.82,
                        metadata={
                            "kb_id": "kb-1",
                            "document_id": "doc-1",
                            "chunk_id": "chunk-1",
                        },
                    )
                ],
            )
        ),
    )
    calls: list[tuple[str, list]] = []
    monkeypatch.setattr(
        al, "record_injected_context", lambda run_id, sources: calls.append((run_id, sources))
    )

    await al.run([{"role": "user", "content": "how deploy?"}])

    assert len(calls) == 1
    assert calls[0][0]
    source = calls[0][1][0]
    assert source.source_id == "chunk-1"
    assert source.source_type == "knowledge"
    assert source.score == 0.82
    assert source.token_estimate == 0
    assert source.metadata == {
        "kb_id": "kb-1",
        "document_id": "doc-1",
        "chunk_id": "chunk-1",
    }


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


async def test_run_stream_records_agent_run_started_trace(mock_client, monkeypatch):
    from fleetent.observability import TraceEvent

    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok"))
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)

    [_ async for _ in al.run_stream("hi", user_id="user-1", agent_name="support-bot")]

    started = next(event for event in events if event.event_type == "agent_run_started")
    assert started.user_id == "user-1"
    assert started.agent_id == "support-bot"
    assert started.payload == {
        "user_id": "user-1",
        "agent_name": "support-bot",
        "entrypoint": "run_stream",
    }


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


async def test_run_stream_records_tool_call_started_and_completed(mock_client, monkeypatch):
    from fleetent.observability import TraceEvent

    async def tool_stream():
        c = MagicMock()
        c.choices = [MagicMock()]
        c.choices[0].delta.content = None
        tc_delta = MagicMock()
        tc_delta.index = 0
        tc_delta.id = "tc-1"
        tc_delta.function.name = "get_time"
        tc_delta.function.arguments = '{"timezone":"UTC"}'
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
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)
    monkeypatch.setattr(al, "get_risk_level", lambda name: "none")
    monkeypatch.setattr(al, "dispatch", lambda name, args: "tool result")

    [_ async for _ in al.run_stream("what time?")]

    started = next(event for event in events if event.event_type == "tool_call_started")
    completed = next(event for event in events if event.event_type == "tool_call_completed")
    assert started.payload["tool_name"] == "get_time"
    assert started.payload["tool_call_id"] == "tc-1"
    assert started.payload["argument_summary"]["keys"] == ["timezone"]
    assert completed.payload["result_summary"]["length"] == len("tool result")


async def test_run_stream_records_final_reply_emitted(mock_client, monkeypatch):
    from fleetent.observability import TraceEvent

    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("hel", "lo"))
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)

    [_ async for _ in al.run_stream("say hello")]

    final = next(event for event in events if event.event_type == "final_reply_emitted")
    assert final.payload["reply_length"] == len("hello")
    assert isinstance(final.payload["elapsed_s"], float)


async def test_run_stream_runtime_events_share_run_id(mock_client, monkeypatch):
    from fleetent.observability import TraceEvent

    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok"))
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)

    [_ async for _ in al.run_stream("say hello")]

    runtime_events = [
        event
        for event in events
        if event.event_type
        in {
            "agent_run_started",
            "llm_call_started",
            "llm_call_completed",
            "final_reply_emitted",
            "agent_run_completed",
        }
    ]
    assert len({event.run_id for event in runtime_events}) == 1


async def test_run_stream_injects_long_term_context_before_model_call(mock_client, monkeypatch):
    from fleetent.intelligence.long_term_ctx import BuiltContext

    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok"))
    build_context = AsyncMock(
        return_value=BuiltContext(text="Use private deployment docs", sources=[])
    )
    monkeypatch.setattr(al, "build_context", build_context)

    [_ async for _ in al.run_stream("how deploy?", user_id="user-1", agent_name="agent-1")]

    build_context.assert_awaited_once_with(
        "user-1", "how deploy?", "agent-1", 512, memory_namespace="default"
    )
    messages = mock_client.chat.completions.create.await_args.kwargs["messages"]
    assert "Use private deployment docs" in messages[0]["content"]


async def test_run_stream_shares_run_id_between_injected_context_and_completion(
    mock_client, monkeypatch
):
    from fleetent.intelligence.long_term_ctx import BuiltContext, ContextSource
    from fleetent.observability import TraceEvent

    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok"))
    monkeypatch.setattr(
        al,
        "build_context",
        AsyncMock(
            return_value=BuiltContext(
                text="Use private deployment docs",
                sources=[
                    ContextSource(
                        source_type="knowledge",
                        source_id="chunk-1",
                        score=0.82,
                        metadata={"kb_id": "kb-1"},
                    )
                ],
            )
        ),
    )
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)

    def capture_injected_context(run_id, sources):
        events.append(
            TraceEvent(
                run_id=run_id,
                event_type="injected_context",
                payload={"sources": sources},
            )
        )

    monkeypatch.setattr(al, "record_injected_context", capture_injected_context)

    [_ async for _ in al.run_stream("how deploy?")]

    injected = next(event for event in events if event.event_type == "injected_context")
    completed = next(event for event in events if event.event_type == "agent_run_completed")
    assert injected.run_id == completed.run_id


async def test_run_stream_records_injected_context_sources(mock_client, monkeypatch):
    from fleetent.intelligence.long_term_ctx import BuiltContext, ContextSource

    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok"))
    monkeypatch.setattr(
        al,
        "build_context",
        AsyncMock(
            return_value=BuiltContext(
                text="Remember deploy docs",
                sources=[
                    ContextSource(
                        source_type="memory",
                        source_id="memory-1",
                        score=1.0,
                        metadata={"type": "fact"},
                    )
                ],
            )
        ),
    )
    calls: list[tuple[str, list]] = []
    monkeypatch.setattr(
        al, "record_injected_context", lambda run_id, sources: calls.append((run_id, sources))
    )

    [_ async for _ in al.run_stream("how deploy?")]

    assert len(calls) == 1
    source = calls[0][1][0]
    assert source.source_id == "memory-1"
    assert source.source_type == "memory"
    assert source.score == 1.0
    assert source.token_estimate == 0
    assert source.metadata == {"type": "fact"}


async def test_run_stream_omits_empty_long_term_context(mock_client, monkeypatch):
    from fleetent.intelligence.long_term_ctx import BuiltContext

    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok"))
    build_context = AsyncMock(return_value=BuiltContext(text="", sources=[]))
    monkeypatch.setattr(al, "build_context", build_context)

    [_ async for _ in al.run_stream("say hello")]

    messages = mock_client.chat.completions.create.await_args.kwargs["messages"]
    assert "[Long-term context]" not in messages[0]["content"]


async def test_agent_runtime_skips_empty_injected_context_sources(mock_client, monkeypatch):
    from fleetent.intelligence.long_term_ctx import BuiltContext

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    monkeypatch.setattr(
        al, "build_context", AsyncMock(return_value=BuiltContext(text="", sources=[]))
    )
    calls: list[tuple[str, list]] = []
    monkeypatch.setattr(
        al, "record_injected_context", lambda run_id, sources: calls.append((run_id, sources))
    )

    await al.run([{"role": "user", "content": "hi"}])

    assert calls == []


def test_run_sync_calls_long_term_context(mock_client, monkeypatch):
    from fleetent.intelligence.long_term_ctx import BuiltContext

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    build_context = AsyncMock(return_value=BuiltContext(text="CLI memory", sources=[]))
    monkeypatch.setattr(al, "build_context", build_context)
    monkeypatch.setattr(al, "scan_skills", lambda: None)

    result = al.run_sync("hello", user_id="user-1")

    assert result == "ok"
    build_context.assert_awaited_once_with("user-1", "hello", "", 512, memory_namespace="default")
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
    monkeypatch.setattr(al, "get_async_client_and_config", lambda *a, **k: (client, cfg))
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


async def test_run_records_model_fallback_triggered(mock_client_fb, monkeypatch):
    from fleetent.observability import TraceEvent

    mock_client_fb.chat.completions.create = AsyncMock(
        side_effect=[_mk_http_error(429, RateLimitError), _text_resp("fallback reply")]
    )
    events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", events.append)

    await al.run([{"role": "user", "content": "hi"}])

    fallback = next(event for event in events if event.event_type == "model_fallback_triggered")
    assert fallback.payload == {
        "from_model": "primary-model",
        "to_model": "fallback-model",
        "reason": "RateLimitError: rate limit",
        "attempt_index": 1,
    }


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


async def test_run_stream_records_agent_run_failed_trace(mock_client_fb, monkeypatch):
    from fleetent.observability import TraceEvent

    mock_client_fb.chat.completions.create = AsyncMock(
        side_effect=[_mk_http_error(429, RateLimitError), _mk_http_error(429, RateLimitError)]
    )
    trace_events: list[TraceEvent] = []
    monkeypatch.setattr(al, "record_trace_event", trace_events.append)

    [_ async for _ in al.run_stream("hi", user_id="user-1")]

    failed = next(event for event in trace_events if event.event_type == "agent_run_failed")
    assert failed.user_id == "user-1"
    assert failed.payload["entrypoint"] == "run_stream"
    assert failed.payload["error_type"] == "RateLimitError"
    assert "rate limit" in failed.payload["error_message"]
    assert isinstance(failed.payload["elapsed_s"], float)


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


# ── snapshot application (task 9) ─────────────────────────────────────────────


def _fn_schema(name: str) -> dict:
    return {"type": "function", "function": {"name": name, "description": "", "parameters": {}}}


def _snapshot(**overrides):
    from fleetent.agent_runtime import AgentSnapshot

    base = dict(
        agent_id=1,
        name="bot",
        version=1,
        version_id=1,
        system_prompt="You are bot.",
        allowed_tools=None,
        skills_dir=None,
        mcp_server_ids=None,
        model_overrides={},
        memory_namespace="default",
    )
    base.update(overrides)
    return AgentSnapshot(**base)


async def test_run_with_snapshot_filters_tools_by_allowed_and_mcp(mock_client, monkeypatch):
    monkeypatch.setattr(
        al,
        "get_schemas",
        lambda: [_fn_schema("shell"), _fn_schema("github__x"), _fn_schema("gitlab__y")],
    )
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    snap = _snapshot(allowed_tools=["shell", "github__*"], mcp_server_ids=["github"])

    await al.run([{"role": "user", "content": "hi"}], snapshot=snap)

    tools = mock_client.chat.completions.create.await_args.kwargs["tools"]
    names = {t["function"]["name"] for t in tools}
    assert names == {"shell", "github__x"}


async def test_run_with_snapshot_passes_model_overrides(mock_client, monkeypatch):
    captured: dict = {}

    def capture(task_type, overrides=None):
        captured["task_type"] = task_type
        captured["overrides"] = overrides
        return mock_client, _route_cfg()

    monkeypatch.setattr(al, "get_async_client_and_config", capture)
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    snap = _snapshot(model_overrides={"default": {"model": "x"}})

    await al.run([{"role": "user", "content": "hi"}], snapshot=snap)

    assert captured["overrides"] == {"default": {"model": "x"}}


async def test_run_with_snapshot_passes_memory_namespace(mock_client, monkeypatch):
    from fleetent.intelligence.long_term_ctx import BuiltContext

    build_context = AsyncMock(return_value=BuiltContext(text="", sources=[]))
    monkeypatch.setattr(al, "build_context", build_context)
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    snap = _snapshot(memory_namespace="analyst")

    await al.run([{"role": "user", "content": "hi"}], snapshot=snap)

    assert build_context.await_args.kwargs.get("memory_namespace") == "analyst"


async def test_run_without_snapshot_uses_default_namespace_and_no_overrides(
    mock_client, monkeypatch
):
    from fleetent.intelligence.long_term_ctx import BuiltContext

    captured: dict = {}

    def capture(task_type, overrides=None):
        captured["overrides"] = overrides
        return mock_client, _route_cfg()

    monkeypatch.setattr(al, "get_async_client_and_config", capture)
    build_context = AsyncMock(return_value=BuiltContext(text="", sources=[]))
    monkeypatch.setattr(al, "build_context", build_context)
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))

    await al.run([{"role": "user", "content": "hi"}])

    assert captured["overrides"] is None
    assert build_context.await_args.kwargs.get("memory_namespace") == "default"


async def test_run_stream_with_snapshot_uses_skills_dir(mock_client, monkeypatch):
    class FakeIndex:
        def __init__(self, skills_dir=None, *, scan=True):
            self.skills_dir = skills_dir

        def match(self, user_input):
            return "deploy"

        def load(self, name):
            return "SKILL-FROM-DIR"

    monkeypatch.setattr(al, "SkillIndex", FakeIndex)
    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok"))
    snap = _snapshot(skills_dir="agents/bot/skills")

    [_ async for _ in al.run_stream("how deploy?", snapshot=snap)]

    messages = mock_client.chat.completions.create.await_args.kwargs["messages"]
    assert "SKILL-FROM-DIR" in messages[0]["content"]


async def test_run_stream_with_snapshot_filters_tools(mock_client, monkeypatch):
    monkeypatch.setattr(
        al,
        "get_schemas",
        lambda: [_fn_schema("shell"), _fn_schema("github__x"), _fn_schema("gitlab__y")],
    )
    mock_client.chat.completions.create = AsyncMock(return_value=_stream_chunks("ok"))
    snap = _snapshot(allowed_tools=["shell", "github__*"], mcp_server_ids=["github"])

    [_ async for _ in al.run_stream("hi", snapshot=snap)]

    tools = mock_client.chat.completions.create.await_args.kwargs["tools"]
    names = {t["function"]["name"] for t in tools}
    assert names == {"shell", "github__x"}


def _route_cfg():
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512
    cfg.fallbacks = ()
    return cfg
