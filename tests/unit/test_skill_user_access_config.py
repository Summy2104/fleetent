"""skill_user_access config field on AgentFile (skill-user-access)."""

from __future__ import annotations

from fleetent.agent_config import AgentFile, default_models


def _agent(**kw) -> AgentFile:
    return AgentFile(name="a", version=1, models=default_models(), **kw)


def test_skill_user_access_defaults_empty() -> None:
    assert _agent().skill_user_access == {}


def test_skill_user_access_settable() -> None:
    af = _agent(skill_user_access={"secret-skill": ["U1", "U2"]})
    assert af.skill_user_access == {"secret-skill": ["U1", "U2"]}
