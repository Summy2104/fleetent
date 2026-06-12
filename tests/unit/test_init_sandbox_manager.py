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


def _construct(agent: AgentFile | None) -> dict:
    with (
        patch("fleetent.integrations.sandbox.factory.create_backend", MagicMock()),
        patch("fleetent.tools.builtin_tools.SandboxManager") as manager_cls,
    ):
        builtin_tools.init_sandbox_manager(agent)
    assert manager_cls.call_count == 1
    return manager_cls.call_args.kwargs


def test_init_forwards_multi_user_true() -> None:
    kwargs = _construct(_agent(multi_user=True))
    assert kwargs["multi_user"] is True


def test_init_forwards_multi_user_false() -> None:
    kwargs = _construct(_agent(multi_user=False))
    assert kwargs["multi_user"] is False


def test_init_without_agent_defaults_single_user() -> None:
    """A standalone run with no AgentFile constructs a single-user manager."""
    kwargs = _construct(None)
    assert kwargs["multi_user"] is False
