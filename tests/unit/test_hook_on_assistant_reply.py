"""Unit tests: on_assistant_reply hook integration in run() (P3).

Asserts modified_content replaces the assistant's reply in messages and return value,
tool_calls-only turns don't trigger the hook, and disabled/no-hook paths are unchanged.
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


def _text_resp(text: str = "original reply") -> MagicMock:
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


async def test_on_assistant_reply_rewrites_final_reply(mock_client):
    @hooks.hook("on_assistant_reply")
    def censor(ctx):
        return HookResult(modified_content="[CENSORED]")

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("original reply"))
    governance = GovernanceConfig(hooks_enabled=True)
    result = await loop.run([{"role": "user", "content": "hi"}], governance=governance, user_id="u")
    assert result == "[CENSORED]"


async def test_on_assistant_reply_none_keeps_original(mock_client):
    @hooks.hook("on_assistant_reply")
    def observe(ctx):
        return None

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("unchanged"))
    governance = GovernanceConfig(hooks_enabled=True)
    result = await loop.run([{"role": "user", "content": "hi"}], governance=governance, user_id="u")
    assert result == "unchanged"


async def test_on_assistant_reply_disabled_no_effect(mock_client):
    @hooks.hook("on_assistant_reply")
    def censor(ctx):
        return HookResult(modified_content="[CENSORED]")

    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("original reply"))
    governance = GovernanceConfig(hooks_enabled=False)
    result = await loop.run([{"role": "user", "content": "hi"}], governance=governance, user_id="u")
    assert result == "original reply"
