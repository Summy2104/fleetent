"""Unit tests: on_user_input hook integration in run_stream() (P3).

Drives run_stream() with mocked LLM + registered on_user_input hook + governance,
asserting deny/modified_content/disabled behavior on the HTTP/streaming path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.runtime.hooks as hooks
import fleetent.runtime.loop as loop
from fleetent.runtime.hooks import HookResult
from fleetent.runtime.snapshot import GovernanceConfig


@pytest.fixture(autouse=True)
def _reset():
    hooks.reset()
    yield
    hooks.reset()


@pytest.fixture
def mock_client(monkeypatch) -> AsyncMock:
    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512
    cfg.params = {}
    cfg.fallbacks = ()

    monkeypatch.setattr(
        loop, "get_async_client_and_config", lambda *a, **kw: (client, cfg), raising=False
    )
    monkeypatch.setattr(loop, "_build_async_client", lambda resolved, api_key: client)
    monkeypatch.setattr(loop, "get_schemas", lambda: [])
    monkeypatch.setattr(loop, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(loop, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(loop, "extract_and_update", AsyncMock())
    monkeypatch.setattr(loop, "dispatch", lambda name, args, **kw: f"{name}_result")
    monkeypatch.setattr(loop, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(
        loop,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns if max_turns is not None else 50,
            max_consecutive_failures if max_consecutive_failures is not None else 3,
        ),
    )
    return client


def _streaming_text(text: str = "hello"):
    """Minimal streaming response yielding one text delta then stopping."""
    delta = MagicMock()
    delta.content = text
    delta.tool_calls = None
    delta.reasoning_content = None
    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = "stop"
    chunk = MagicMock()
    chunk.choices = [choice]
    chunk.usage = None

    async def _gen():
        yield chunk

    resp = AsyncMock()
    resp.__aiter__ = lambda s: _gen().__aiter__()
    resp.usage = None
    return resp


async def _stream(user_input: str, governance: GovernanceConfig) -> list[dict]:
    events = []
    async for ev in loop.run_stream(user_input, governance=governance, principal=None):
        events.append(ev)
    return events


async def test_on_user_input_deny_yields_error_and_stops(mock_client):
    @hooks.hook("on_user_input")
    def block(ctx):
        if "spam" in ctx.payload["content"]:
            return HookResult(decision="deny", reason="spam detected")
        return None

    mock_client.chat.completions.create = AsyncMock(return_value=_streaming_text())
    governance = GovernanceConfig(hooks_enabled=True)
    events = await _stream("this is spam", governance)
    types = [e["type"] for e in events]
    assert "error" in types
    assert "done" not in types  # stopped before done


async def test_on_user_input_modified_content_replaces_input(mock_client):
    @hooks.hook("on_user_input")
    def rewrite(ctx):
        return HookResult(modified_content="[SANITIZED]")

    # Capture the messages sent to LLM to check user content
    captured: list = []

    async def fake_create(**kw):
        captured.extend(kw.get("messages", []))
        return _streaming_text("ok")

    mock_client.chat.completions.create = fake_create
    governance = GovernanceConfig(hooks_enabled=True)
    await _stream("original input", governance)
    user_msgs = [m for m in captured if m.get("role") == "user"]
    contents = [m.get("content", "") for m in user_msgs]
    assert any("[SANITIZED]" in str(c) for c in contents)
    assert not any("original input" in str(c) for c in contents)


async def test_on_user_input_disabled_no_effect(mock_client):
    @hooks.hook("on_user_input")
    def block(ctx):
        return HookResult(decision="deny", reason="should not run")

    mock_client.chat.completions.create = AsyncMock(return_value=_streaming_text("hello"))
    governance = GovernanceConfig(hooks_enabled=False)
    events = await _stream("hi there", governance)
    types = [e["type"] for e in events]
    assert "done" in types
    assert "error" not in types
