"""skill_hot_reload config flag on AgentFile (skill-external-hot-reload)."""

from __future__ import annotations

from fleetent.agent_config import AgentFile, default_models


def _agent(**kw) -> AgentFile:
    return AgentFile(name="a", version=1, models=default_models(), **kw)


def test_skill_hot_reload_defaults_true() -> None:
    assert _agent().skill_hot_reload is True


def test_skill_hot_reload_settable_false() -> None:
    assert _agent(skill_hot_reload=False).skill_hot_reload is False
