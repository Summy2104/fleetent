"""Unit tests: pre_llm_call hook integration in run() (P3).

Asserts inject_context appends to messages before LLM call, and disabled/no-hook paths
leave messages unchanged.
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
    monkeypatch.setattr(loop, "run_pipeline_from_conversation", AsyncMock())
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


async def test_pre_llm_call_inject_context_appended_to_messages(mock_client):
    @hooks.hook("pre_llm_call")
    def inject(ctx):
        return HookResult(inject_context="[ENTERPRISE POLICY: always be helpful]")

    captured: list = []

    async def fake_create(**kw):
        captured.extend(kw.get("messages", []))
        return _text_resp("ok")

    mock_client.chat.completions.create = fake_create
    governance = GovernanceConfig(hooks_enabled=True)
    await loop.run([{"role": "user", "content": "hi"}], governance=governance, principal=None)
    injected = [m for m in captured if "[ENTERPRISE POLICY" in str(m.get("content", ""))]
    assert len(injected) >= 1


async def test_pre_llm_call_none_no_change(mock_client):
    @hooks.hook("pre_llm_call")
    def observe(ctx):
        return None

    captured: list = []

    async def fake_create(**kw):
        captured.extend(kw.get("messages", []))
        return _text_resp("ok")

    mock_client.chat.completions.create = fake_create
    governance = GovernanceConfig(hooks_enabled=True)
    await loop.run([{"role": "user", "content": "hi"}], governance=governance, principal=None)
    # No injection
    assert not any("[ENTERPRISE" in str(m.get("content", "")) for m in captured)


async def test_pre_llm_call_disabled_no_effect(mock_client):
    @hooks.hook("pre_llm_call")
    def inject(ctx):
        return HookResult(inject_context="should not appear")

    captured: list = []

    async def fake_create(**kw):
        captured.extend(kw.get("messages", []))
        return _text_resp("ok")

    mock_client.chat.completions.create = fake_create
    governance = GovernanceConfig(hooks_enabled=False)
    await loop.run([{"role": "user", "content": "hi"}], governance=governance, principal=None)
    assert not any("should not appear" in str(m.get("content", "")) for m in captured)
