"""Tests for snapshot routing without bindings (restructure-agent-access)."""

from typing import Any

from fleetent import agent_config
from fleetent.agent_config import AgentConfigIndex, AgentFile
from fleetent.runtime import snapshot


def _agent_file(name: str = "default") -> AgentFile:
    return AgentFile(
        name=name,
        version=1,
        models={
            "targets": [
                {
                    "id": "primary",
                    "provider": "local",
                    "protocol": "openai_chat",
                    "base_url": "http://local.test/v1/",
                    "model": "text",
                }
            ],
            "routes": {"default": [{"target": "primary"}]},
        },
    )


def _index(**overrides: Any) -> AgentConfigIndex:
    base: dict[str, Any] = {"agents": {}, "default": None}
    base.update(overrides)
    return AgentConfigIndex(**base)


# ── Task 4.1: snapshot 路径不再调用 agent_for_channel/agent_for_user ─────────


def test_resolve_agent_for_request_uses_only_default(monkeypatch: Any) -> None:
    """Channel and user args are ignored; only default_agent() is consulted."""
    agent = _agent_file("default")
    index = _index(agents={"default": agent}, default="default")
    monkeypatch.setattr(agent_config, "current", lambda: index)

    snap = snapshot.resolve_agent_for_request("slack", "C_irrelevant", "U_irrelevant")
    assert snap is not None and snap.name == "default"


def test_resolve_agent_for_request_none_when_no_default(monkeypatch: Any) -> None:
    monkeypatch.setattr(agent_config, "current", lambda: _index())
    assert snapshot.resolve_agent_for_request(None, None, None) is None


def test_index_has_no_by_channel_field(monkeypatch: Any) -> None:
    index = _index()
    assert not hasattr(index, "by_channel")


def test_index_has_no_by_user_field(monkeypatch: Any) -> None:
    index = _index()
    assert not hasattr(index, "by_user")
