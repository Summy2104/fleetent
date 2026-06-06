"""One-shot `fleetent "<prompt>"` (run_sync) applies the deployed home/default agent."""

from unittest.mock import AsyncMock

import yaml

import fleetent.runtime.loop as loop
from fleetent import agent_config
from fleetent.integrations.sandbox import enablement as se


def _write_home_agent(home, **fields):
    agent_home = home / "agents" / "default"
    agent_home.mkdir(parents=True, exist_ok=True)
    doc = {
        "name": "deployed",
        "version": 1,
        "models": agent_config.default_models().model_dump(mode="json"),
    }
    doc.update(fields)
    (agent_home / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def test_run_sync_applies_home_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.delenv("FLEETENT_AGENTS_DIR", raising=False)
    _write_home_agent(
        tmp_path,
        system_prompt="You are the DEPLOYED agent.",
        allowed_tools=["shell"],
        allowed_skills=["weather"],
    )

    captured = {}

    async def fake_run(messages, **kwargs):
        captured.update(kwargs)
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(loop, "run", fake_run)
    monkeypatch.setattr(se, "get_effective_mode", AsyncMock(return_value=se.Mode.OFF))

    result = loop.run_sync("你好")

    assert result == "ok"
    assert captured["system_prompt"] == "You are the DEPLOYED agent."
    assert captured["allowed_tools"] == ["shell"]
    assert captured["allowed_skills"] == ["weather"]
    assert captured["agent_name"] == "deployed"
    # the deployed system prompt is what went into the assembled messages, not _SYSTEM
    assert "DEPLOYED" in captured["messages"][0]["content"]
    assert loop._SYSTEM not in captured["messages"][0]["content"]


def test_run_sync_no_agent_uses_generic_default(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.delenv("FLEETENT_AGENTS_DIR", raising=False)
    # no default Agent home and no explicit agents dir → no default agent

    captured = {}

    async def fake_run(messages, **kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(loop, "run", fake_run)
    monkeypatch.setattr(se, "get_effective_mode", AsyncMock(return_value=se.Mode.OFF))

    loop.run_sync("hi")

    assert captured["system_prompt"] == loop._SYSTEM
    assert captured.get("allowed_tools") is None
