"""skill_authoring_enabled config + schema-build gating of skill_manage (agent-skill-tools)."""

from __future__ import annotations

from fleetent.agent_config import AgentFile, default_models


def _agent(**kw) -> AgentFile:
    return AgentFile(name="a", version=1, models=default_models(), **kw)


# --- config field (task 3.1/3.2) ---


def test_skill_authoring_enabled_defaults_false() -> None:
    assert _agent().skill_authoring_enabled is False


def test_skill_authoring_enabled_settable() -> None:
    assert _agent(skill_authoring_enabled=True).skill_authoring_enabled is True


# --- schema-build gating (task 3.3/3.4) ---


def _schemas() -> list[dict]:
    return [
        {"type": "function", "function": {"name": "read_skill"}},
        {"type": "function", "function": {"name": "skill_manage"}},
        {"type": "function", "function": {"name": "list_skills"}},
    ]


def test_skill_manage_hidden_when_authoring_disabled() -> None:
    from fleetent.runtime.loop import _filter_skill_authoring

    out = _filter_skill_authoring(_schemas(), enabled=False)
    names = {s["function"]["name"] for s in out}
    assert "skill_manage" not in names
    assert {"read_skill", "list_skills"} <= names


def test_skill_manage_visible_when_authoring_enabled() -> None:
    from fleetent.runtime.loop import _filter_skill_authoring

    out = _filter_skill_authoring(_schemas(), enabled=True)
    names = {s["function"]["name"] for s in out}
    assert "skill_manage" in names
