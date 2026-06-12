"""Integration: the multi_user signal flows agent.yaml → init_sandbox_manager → guard.

End-to-end wiring (sandbox-scope-split-followups): an agent that declares
`sandbox.multi_user: true` plus a platform `workspace_scope: agent` must have its
scope corrected to `session` by the manager's guard; a single-user agent keeps
`agent`. Exercises real config-file loading + manager `__post_init__` orchestration
(not a pure parse), so it lives at integration level.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from fleetent.agent_config import AgentFile, default_models
from fleetent.integrations.sandbox import config as sandbox_config
from fleetent.integrations.sandbox.manager import WorkspaceScope
from fleetent.tools import builtin_tools


def _write_agent_scope_settings(tmp_path: Path) -> Path:
    path = tmp_path / "platform.yaml"
    path.write_text(
        textwrap.dedent(
            """
            sandbox:
              workspace_scope: agent
            """
        )
    )
    return path


def _agent(*, multi_user: bool) -> AgentFile:
    return AgentFile(
        name="support",
        version=1,
        models=default_models(),
        sandbox={"multi_user": multi_user},
    )


@pytest.fixture(autouse=True)
def _agent_scope_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", _write_agent_scope_settings(tmp_path))
    # init_sandbox_manager mutates the module-global `_MANAGER`; restore it so the
    # constructed manager does not leak into later tests that call `_get_manager`.
    saved = builtin_tools._MANAGER
    try:
        yield
    finally:
        builtin_tools._MANAGER = saved


def test_multi_user_agent_scope_corrected_to_session() -> None:
    mgr = builtin_tools.init_sandbox_manager(_agent(multi_user=True))
    assert mgr.multi_user is True
    assert mgr.scope is WorkspaceScope.SESSION


def test_single_user_agent_scope_preserved() -> None:
    mgr = builtin_tools.init_sandbox_manager(_agent(multi_user=False))
    assert mgr.multi_user is False
    assert mgr.scope is WorkspaceScope.AGENT
