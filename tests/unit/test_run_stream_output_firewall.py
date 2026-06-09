"""Output firewall on the run_stream path (output-firewall, task 2).

The streaming loop yields a `tool_result` event AND appends to messages; a secret in a
tool result must be redacted before both. Mocks the LLM (a streamed tool call then a
text turn) and dispatch (returns a secret), then asserts the streamed event is masked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.runtime.loop as al

_SECRET = "sk-ant-abcdefgh12345678"


@pytest.fixture
def mock_client(monkeypatch) -> AsyncMock:
    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512
    cfg.params = {}
    cfg.fallbacks = ()
    monkeypatch.setattr(
        al, "get_async_client_and_config", lambda *a, **kw: (client, cfg), raising=False
    )
    monkeypatch.setattr(al, "_build_async_client", lambda resolved, api_key: client)
    monkeypatch.setattr(al, "get_schemas", lambda: [])
    monkeypatch.setattr(al, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(al, "extract_and_update", AsyncMock())
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(al, "get_risk_level", lambda name: "none")
    monkeypatch.setattr(al, "dispatch", lambda name, args, **kw: f"leaked {_SECRET} here")
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns if max_turns is not None else 50,
            max_consecutive_failures if max_consecutive_failures is not None else 3,
        ),
    )
    return client


async def _stream_tool_call(name: str, call_id: str = "tc-1"):
    c = MagicMock()
    c.usage = None
    c.choices = [MagicMock()]
    d = c.choices[0].delta
    d.content = None
    d.reasoning_content = None
    tc = MagicMock()
    tc.index = 0
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = "{}"
    d.tool_calls = [tc]
    c.choices[0].finish_reason = "tool_calls"
    yield c


async def _stream_text(text: str):
    c = MagicMock()
    c.usage = None
    c.choices = [MagicMock()]
    c.choices[0].delta.content = text
    c.choices[0].delta.tool_calls = None
    c.choices[0].delta.reasoning_content = None
    c.choices[0].finish_reason = "stop"
    yield c


async def test_run_stream_redacts_tool_result_event(mock_client) -> None:
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[_stream_tool_call("read_file"), _stream_text("done")]
    )
    events = [e async for e in al.run_stream("go")]
    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert tool_results, "expected a tool_result event"
    assert _SECRET not in tool_results[0]["content"]
    assert "[REDACTED]" in tool_results[0]["content"]
