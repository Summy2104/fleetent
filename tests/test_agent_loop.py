"""Unit tests for agent_loop.run() and run_stream()."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import mini_agent.agent_loop as al


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
        c.choices = [MagicMock()]
        c.choices[0].delta.content = content
        c.choices[0].delta.tool_calls = None
        c.choices[0].finish_reason = finish if i == len(contents) - 1 else None
        yield c


@pytest.fixture
def mock_client(monkeypatch) -> AsyncMock:
    """Patch all external I/O in agent_loop, return the mock LLM client."""
    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512

    monkeypatch.setattr(al, "get_async_client_and_config", lambda _: (client, cfg))
    monkeypatch.setattr(al, "get_schemas", lambda: [])
    monkeypatch.setattr(al, "maybe_compress", lambda msgs: msgs)
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(al, "extract_and_save", lambda *a, **kw: None)
    monkeypatch.setattr(al, "dispatch", lambda name, args, **kw: f"{name}_result")
    monkeypatch.setattr(al, "load_memories", lambda **kw: "")
    monkeypatch.setattr(al, "match_skill", lambda _: None)
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

    with patch.object(al, "get_schemas", return_value=[
        {"function": {"name": "sub_agent"}},
        {"function": {"name": "get_time"}},
    ]):
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

    with patch.object(al, "get_schemas", return_value=[
        {"function": {"name": "sub_agent"}},
        {"function": {"name": "get_time"}},
    ]):
        await al.run([{"role": "user", "content": "go"}])

    names = [s["function"]["name"] for s in schemas_used[0]]
    assert "sub_agent" in names


# ── run_stream() ──────────────────────────────────────────────────────────────


async def test_run_stream_yields_text_deltas_and_done(mock_client):
    mock_client.chat.completions.create = AsyncMock(
        return_value=_stream_chunks("hel", "lo", None)
    )

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

    mock_client.chat.completions.create = AsyncMock(
        side_effect=[tool_stream(), text_stream()]
    )

    events = [e async for e in al.run_stream("what time?")]

    types = [e["type"] for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    assert "text_delta" in types
    assert "done" in types

    tool_event = next(e for e in events if e["type"] == "tool_call")
    assert tool_event["name"] == "get_time"


async def test_run_sub_agent_tool_intercepted_and_executed(mock_client):
    """sub_agent tool call is intercepted by agent_loop, not passed to dispatch."""
    from mini_agent.sub_agent import SubAgentResult

    tasks_json = '[{"name": "t1", "prompt": "do it"}]'
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[
            _tool_resp("sub_agent", f'{{"tasks": "{tasks_json.replace(chr(34), chr(92)+chr(34))}"}}'  ),
            _text_resp("all done"),
        ]
    )

    fake_results = [SubAgentResult(name="t1", result="task result", error=None, parent_session_id="")]

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
    from mini_agent.sub_agent import SubAgentResult

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
