"""Unit tests for `init_sandbox_manager` wiring the multi_user signal.

The process sandbox manager's `multi_user` guard only triggers when its sole
construction site (`init_sandbox_manager`) forwards the agent.yaml
`sandbox.multi_user` value (sandbox-scope-split-followups). These tests mock the
manager + backend factory so they stay at unit level (no real Docker / DB).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fleetent.agent_config import AgentFile, default_models
from fleetent.tools import builtin_tools


@pytest.fixture(autouse=True)
def _restore_process_manager():
    """init_sandbox_manager mutates the module-global `_MANAGER`; restore it so a
    mocked manager does not leak into later tests that call `_get_manager`."""
    saved = builtin_tools._MANAGER
    try:
        yield
    finally:
        builtin_tools._MANAGER = saved


def _agent(*, multi_user: bool) -> AgentFile:
    return AgentFile(
        name="support",
        version=1,
        models=default_models(),
        sandbox={"multi_user": multi_user},
    )


def _agent_with_skill_source(source: str | None) -> AgentFile:
    return AgentFile(
        name="support",
        version=1,
        models=default_models(),
        sandbox={"skill_mount": {"source": source}},
    )


def _construct(agent: AgentFile | None, **kwargs) -> dict:
    with (
        patch("fleetent.integrations.sandbox.factory.create_backend", MagicMock()),
        patch("fleetent.tools.builtin_tools.SandboxManager") as manager_cls,
    ):
        builtin_tools.init_sandbox_manager(agent, **kwargs)
    assert manager_cls.call_count == 1
    return manager_cls.call_args.kwargs


def test_init_forwards_multi_user_true() -> None:
    kwargs = _construct(_agent(multi_user=True))
    assert kwargs["multi_user"] is True


def test_init_forwards_multi_user_false() -> None:
    kwargs = _construct(_agent(multi_user=False))
    assert kwargs["multi_user"] is False


def test_init_without_agent_defaults_fail_safe() -> None:
    """Fail-safe: a run with no AgentFile constructs a multi-user manager
    (forces per-user session isolation; harmless for a single-process one-shot)."""
    kwargs = _construct(None)
    assert kwargs["multi_user"] is True


def test_per_agent_skills_root_is_default_source_when_unset() -> None:
    """sandbox-skill-mount-per-agent-root: when the agent leaves skill_mount.source
    unset, the per-agent skills root passed by boot becomes the mount source default
    (so the mount root == the scan root), instead of the global <base>/skills."""
    per_agent = "/home/.fleetent/agents/support/skills"
    kwargs = _construct(_agent_with_skill_source(None), agent_skills_root=per_agent)
    assert kwargs["skill_mount"].source == per_agent


def test_explicit_skill_source_wins_over_per_agent_root() -> None:
    """An explicitly configured skill_mount.source takes precedence over the
    per-agent default."""
    kwargs = _construct(
        _agent_with_skill_source("/operator/custom/skills"),
        agent_skills_root="/home/.fleetent/agents/support/skills",
    )
    assert kwargs["skill_mount"].source == "/operator/custom/skills"


def test_no_skills_root_keeps_global_fallback() -> None:
    """Backward compat: a call without agent_skills_root keeps source as the agent's
    own value (None → manager falls back to the global effective root as before)."""
    kwargs = _construct(_agent_with_skill_source(None))
    assert kwargs["skill_mount"].source is None
