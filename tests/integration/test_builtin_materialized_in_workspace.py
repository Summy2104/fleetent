"""Integration: package builtin skill materialized + reachable in container (D3).

Skipped when docker is unavailable. A package builtin skill (with a same-directory
resource) is materialized into the effective user root, mounted at /workspace/skills,
and its resource is readable at `$SKILLS_DIR/<name>/<resource>` inside the container.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from fleetent import paths
from fleetent.integrations.sandbox.client import SandboxClient
from fleetent.integrations.sandbox.config import SandboxResources, SkillMountConfig
from fleetent.integrations.sandbox.manager import SandboxManager, Scope
from fleetent.skills import registry


def _docker_available() -> bool:
    try:
        return subprocess.run(["docker", "version"], capture_output=True).returncode == 0
    except (FileNotFoundError, OSError):
        return False


pytestmark = pytest.mark.skipif(not _docker_available(), reason="docker not available")


@pytest.fixture
def workspace_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "workspaces"
    monkeypatch.setattr(paths, "workspaces_dir", lambda: root)
    return root


async def test_builtin_resource_reachable_in_container(
    workspace_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A package builtin skill with a co-located resource.
    builtin = tmp_path / "builtin_skills" / "starter"
    builtin.mkdir(parents=True)
    (builtin / "SKILL.md").write_text("---\nname: starter\ndescription: d\n---\nbody")
    (builtin / "asset.bin").write_text("builtin-asset")
    monkeypatch.setattr(registry, "BUILTIN_SKILLS_DIR", tmp_path / "builtin_skills")

    user_root = tmp_path / "user_skills"
    mgr = SandboxManager(
        backend=SandboxClient(),
        scope=Scope.SESSION,
        resources_by_scope={"session": SandboxResources(), "agent": SandboxResources()},
        skill_mount=SkillMountConfig(enabled=True, read_only=True, source=str(user_root)),
    )
    try:
        ws = await mgr.acquire(Scope.SESSION, "mat-sess", "bot")
        res = await mgr.backend.exec(ws, "cat /workspace/skills/starter/asset.bin")
        assert res.stdout.strip() == "builtin-asset"
    finally:
        await mgr.backend.destroy_workspace(mgr.container_name(Scope.SESSION, "mat-sess", "bot"))
