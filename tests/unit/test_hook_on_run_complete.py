"""Unit tests: on_run_complete hook in run() (P4)."""

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


async def test_on_run_complete_called_with_reply(mock_client):
    observed: list[dict] = []

    @hooks.hook("on_run_complete")
    def audit(ctx):
        observed.append(dict(ctx.payload))
        return None

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("final answer"))
    governance = GovernanceConfig(hooks_enabled=True)
    result = await loop.run([{"role": "user", "content": "hi"}], governance=governance, principal=None)
    assert result == "final answer"
    assert len(observed) == 1
    assert observed[0]["reply"] == "final answer"


async def test_on_run_complete_return_does_not_affect_reply(mock_client):
    @hooks.hook("on_run_complete")
    def modify(ctx):
        return HookResult(modified_content="should not change reply")

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("original"))
    governance = GovernanceConfig(hooks_enabled=True)
    result = await loop.run([{"role": "user", "content": "hi"}], governance=governance, principal=None)
    assert result == "original"


async def test_on_run_complete_disabled_not_called(mock_client):
    called: list[bool] = []

    @hooks.hook("on_run_complete")
    def track(ctx):
        called.append(True)
        return None

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("reply"))
    governance = GovernanceConfig(hooks_enabled=False)
    await loop.run([{"role": "user", "content": "hi"}], governance=governance, principal=None)
    assert called == []
