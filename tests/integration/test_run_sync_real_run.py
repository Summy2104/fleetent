"""One-shot CLI path must enter the real async run() with a Principal, not user_id."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import yaml

import fleetent.runtime.loop as loop
from fleetent import agent_config


def _write_home_agent(home, **fields) -> None:
    agent_home = home / "agents" / "default"
    agent_home.mkdir(parents=True, exist_ok=True)
    doc = {
        "name": "default",
        "version": 1,
        "system_prompt": "You are the deployed agent.",
        "models": agent_config.default_models().model_dump(mode="json"),
    }
    doc.update(fields)
    (agent_home / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def _text_response(text: str) -> MagicMock:
    message = MagicMock()
    message.content = text
    message.tool_calls = None
    message.model_dump = lambda: {"role": "assistant", "content": text}

    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    response.usage = SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    return response


def test_run_sync_executes_real_run_with_model_boundary_stubbed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.delenv("FLEETENT_AGENTS_DIR", raising=False)
    _write_home_agent(tmp_path)

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace()))
    fake_client.chat.completions.create = AsyncMock(return_value=_text_response("56"))

    monkeypatch.setattr(loop, "_build_async_client", lambda resolved, api_key: fake_client)
    monkeypatch.setattr(loop, "run_pipeline_from_conversation", AsyncMock())

    assert loop.run_sync("What is 7 * 8?", user_id="alice") == "56"
