"""Sandbox skill mount accepts a per-session view path as source (skill-user-access)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fleetent.integrations.sandbox.config import SandboxResources, SkillMountConfig
from fleetent.integrations.sandbox.manager import SandboxManager, Scope


@pytest.fixture
def workspaces(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    from fleetent import paths

    monkeypatch.setattr(paths, "workspaces_dir", lambda: tmp_path / "ws")
    return tmp_path


def _client() -> MagicMock:
    c = MagicMock()
    c.capabilities = MagicMock(workspace_mount=True, persist_workspace=False)
    return c


def _mgr(skills: Path) -> SandboxManager:
    return SandboxManager(
        backend=_client(),
        scope=Scope.SESSION,
        resources_by_scope={"session": SandboxResources(), "agent": SandboxResources()},
        skill_mount=SkillMountConfig(enabled=True, read_only=True, source=str(skills)),
    )


def test_source_override_used_as_mount_source(workspaces, tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    view = tmp_path / "skills" / ".views" / "sess-1"
    view.mkdir(parents=True)
    sm = _mgr(skills)._resolve_skill_mount(source_override=str(view))
    assert sm is not None
    assert sm.host_src == str(view)  # the per-session view, not the full root
    assert sm.read_only is True


def test_no_override_uses_full_root(workspaces, tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    sm = _mgr(skills)._resolve_skill_mount()
    assert sm is not None
    assert sm.host_src == str(skills)  # unchanged behavior


def test_blocked_override_rejected(workspaces, tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    with pytest.raises(ValueError, match="blocked"):
        _mgr(skills)._resolve_skill_mount(source_override="/etc")
