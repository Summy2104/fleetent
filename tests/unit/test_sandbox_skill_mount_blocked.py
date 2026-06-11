"""Unit tests: skills mount source guarded by is_blocked_mount (sandbox-skill-mount).

A skills host source resolving under a sensitive root (~/.ssh, /etc, ...) must be
rejected before any container is created. Mock backend + tmp workspace; no docker.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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
    c.find_workspace = AsyncMock(return_value=None)
    c.inspect_config_hash = AsyncMock(return_value=None)
    c.destroy_workspace = AsyncMock()
    c.create_workspace = AsyncMock(return_value="cid")
    c.image_exists = AsyncMock(return_value=False)
    c.capabilities = MagicMock(workspace_mount=True, persist_workspace=False)
    return c


def _mgr(client: MagicMock, skill_cfg: SkillMountConfig) -> SandboxManager:
    return SandboxManager(
        backend=client,
        scope=Scope.SESSION,
        resources_by_scope={"session": SandboxResources(), "agent": SandboxResources()},
        skill_mount=skill_cfg,
    )


async def test_blocked_skills_source_rejected(workspaces: Path) -> None:
    c = _client()
    cfg = SkillMountConfig(enabled=True, read_only=True, source="/etc")
    mgr = _mgr(c, cfg)
    with pytest.raises(ValueError, match="blocked"):
        await mgr.acquire(Scope.SESSION, "sess", "bot")
    c.create_workspace.assert_not_awaited()


async def test_allowed_skills_source_threads_skill_mount(workspaces: Path, tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skills.mkdir()
    c = _client()
    cfg = SkillMountConfig(enabled=True, read_only=True, source=str(skills))
    mgr = _mgr(c, cfg)
    await mgr.acquire(Scope.SESSION, "sess", "bot")
    sm = c.create_workspace.await_args.kwargs["skill_mount"]
    assert sm is not None
    assert sm.host_src == str(skills)
    assert sm.read_only is True


async def test_disabled_skill_mount_threads_none(workspaces: Path, tmp_path: Path) -> None:
    c = _client()
    cfg = SkillMountConfig(enabled=False, read_only=True, source=str(tmp_path / "skills"))
    mgr = _mgr(c, cfg)
    await mgr.acquire(Scope.SESSION, "sess", "bot")
    assert c.create_workspace.await_args.kwargs["skill_mount"] is None
