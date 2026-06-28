"""Standalone connector baseline: no platform tables, consent degradation, run completes."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import fleetent.runtime.loop as loop_mod
from fleetent.identity import Principal
from fleetent.tools import builtin_tools  # noqa: F401  # load-bearing registration


def _tool_resp(name: str, args: str = "{}", call_id: str = "tc-1") -> MagicMock:
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = args

    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    msg.refusal = None
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
    resp.usage = SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    return resp


def _text_resp(text: str) -> MagicMock:
    msg = MagicMock()
    msg.content = text
    msg.tool_calls = None
    msg.refusal = None
    msg.model_dump = lambda: {"role": "assistant", "content": text}

    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    return resp


async def test_standalone_run_degrades_connector_tool_to_consent_without_platform_tables(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512
    cfg.params = {}
    cfg.fallbacks = ()

    responses = [
        _tool_resp("github_connection_status"),
        _text_resp("done"),
    ]
    calls: list[dict[str, object]] = []

    async def fake_create(**kwargs):
        calls.append(kwargs)
        return responses[len(calls) - 1]

    client.chat.completions.create = fake_create

    monkeypatch.setattr(
        loop_mod, "get_async_client_and_config", lambda *a, **kw: (client, cfg), raising=False
    )
    monkeypatch.setattr(loop_mod, "_build_async_client", lambda resolved, api_key: client)
    monkeypatch.setattr(loop_mod, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(loop_mod, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(loop_mod, "run_pipeline_from_conversation", AsyncMock())
    monkeypatch.setattr(loop_mod, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(
        loop_mod,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns if max_turns is not None else 50,
            max_consecutive_failures if max_consecutive_failures is not None else 3,
        ),
    )

    result = await loop_mod.run(
        messages=[{"role": "user", "content": "check github"}],
        principal=Principal(user_id="user-1", tenant_id="default"),
    )

    assert result == "done"
    assert len(calls) == 2
    tool_messages = [
        message
        for message in calls[1]["messages"]
        if isinstance(message, dict) and message.get("role") == "tool"
    ]
    assert len(tool_messages) == 1
    tool_content = str(tool_messages[0]["content"])
    assert "requires authorization" in tool_content
    assert "github" in tool_content
    assert "https://consent.invalid/github" in tool_content
