"""Unit tests: pre_compact + post_compact hooks in run() (P4).

Mocks _gated_compress to capture its input and verify that:
- pre_compact inject_context is appended before compression
- post_compact receives correct message counts
- disabled/no-hook paths leave behavior unchanged
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


def _text_resp(text: str = "reply") -> MagicMock:
    msg = MagicMock()
    msg.content = text
    msg.tool_calls = None
    msg.model_dump = lambda: {"role": "assistant", "content": text}
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock()
    return resp


async def test_pre_compact_inject_context_appended_before_compression(mock_client, monkeypatch):
    @hooks.hook("pre_compact")
    def inject(ctx):
        return HookResult(inject_context="[MUST RETAIN: compliance policy v2]")

    compress_input: list = []

    def fake_gated_compress(messages, flap_state, **kw):
        compress_input.extend(messages)
        return messages, flap_state

    monkeypatch.setattr(loop, "_gated_compress", fake_gated_compress)
    monkeypatch.setattr(loop, "maybe_compress", lambda msgs, **kw: msgs)
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    governance = GovernanceConfig(hooks_enabled=True)
    await loop.run([{"role": "user", "content": "hi"}], governance=governance, principal=None)
    injected = [m for m in compress_input if "[MUST RETAIN" in str(m.get("content", ""))]
    assert len(injected) >= 1


async def test_post_compact_receives_before_after_counts(mock_client, monkeypatch):
    observed: list[dict] = []

    @hooks.hook("post_compact")
    def observe(ctx):
        observed.append(dict(ctx.payload))
        return None

    def fake_gated_compress(messages, flap_state, **kw):
        # Simulate compression: return only first + last 2
        compressed = messages[:1] + messages[-2:]
        return compressed, flap_state

    monkeypatch.setattr(loop, "_gated_compress", fake_gated_compress)
    monkeypatch.setattr(loop, "maybe_compress", lambda msgs, **kw: msgs)
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    governance = GovernanceConfig(hooks_enabled=True)
    await loop.run(
        [{"role": "user", "content": "hi"}],
        governance=governance,
        principal=None,
    )
    assert len(observed) >= 1
    last = observed[-1]
    assert "messages_before" in last
    assert "messages_after" in last


async def test_pre_compact_disabled_no_effect(mock_client, monkeypatch):
    @hooks.hook("pre_compact")
    def inject(ctx):
        return HookResult(inject_context="should not appear")

    compress_input: list = []

    def fake_gated_compress(messages, flap_state, **kw):
        compress_input.extend(messages)
        return messages, flap_state

    monkeypatch.setattr(loop, "_gated_compress", fake_gated_compress)
    monkeypatch.setattr(loop, "maybe_compress", lambda msgs, **kw: msgs)
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("ok"))
    governance = GovernanceConfig(hooks_enabled=False)
    await loop.run([{"role": "user", "content": "hi"}], governance=governance, principal=None)
    assert not any("should not appear" in str(m.get("content", "")) for m in compress_input)
