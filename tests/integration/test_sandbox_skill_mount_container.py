"""Integration tests: skills bind-mount into a real docker container (sandbox-skill-mount).

Skipped when docker is unavailable (established sandbox skip guard). Asserts the host
skills root is mounted at /workspace/skills, readable in-container, ro write is denied,
`$SKILLS_DIR` == /workspace/skills, and a changed mount source triggers a config_hash
rebuild.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from fleetent import paths
from fleetent.integrations.sandbox.client import SandboxClient
from fleetent.integrations.sandbox.config import SandboxResources, SkillMountConfig
from fleetent.integrations.sandbox.manager import SandboxManager, Scope


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


def _skills_dir(tmp_path: Path) -> Path:
    d = tmp_path / "skills" / "demo"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: demo\ndescription: d\n---\nbody")
    (d / "data.txt").write_text("resource-bytes")
    return tmp_path / "skills"


def _mgr(skills_root: Path, *, read_only: bool = True) -> SandboxManager:
    return SandboxManager(
        backend=SandboxClient(),
        scope=Scope.SESSION,
        resources_by_scope={"session": SandboxResources(), "agent": SandboxResources()},
        skill_mount=SkillMountConfig(enabled=True, read_only=read_only, source=str(skills_root)),
    )


async def _cleanup(mgr: SandboxManager, session_id: str) -> None:
    await mgr.backend.destroy_workspace(mgr.container_name(Scope.SESSION, session_id, "bot"))


async def test_skills_mounted_readable_and_skills_dir_env(
    workspace_root: Path, tmp_path: Path
) -> None:
    skills = _skills_dir(tmp_path)
    mgr = _mgr(skills)
    try:
        ws = await mgr.acquire(Scope.SESSION, "sk-sess", "bot")
        res = await mgr.backend.exec(ws, "cat /workspace/skills/demo/data.txt")
        assert res.stdout.strip() == "resource-bytes"
        env = await mgr.backend.exec(ws, "echo $SKILLS_DIR")
        assert env.stdout.strip() == "/workspace/skills"
    finally:
        await _cleanup(mgr, "sk-sess")


async def test_skills_read_only_write_denied(workspace_root: Path, tmp_path: Path) -> None:
    skills = _skills_dir(tmp_path)
    mgr = _mgr(skills, read_only=True)
    try:
        ws = await mgr.acquire(Scope.SESSION, "sk-ro", "bot")
        res = await mgr.backend.exec(ws, "echo x > /workspace/skills/demo/new.txt; echo $?")
        assert res.stdout.strip().splitlines()[-1] != "0"
    finally:
        await _cleanup(mgr, "sk-ro")


async def test_skills_source_change_rebuilds(workspace_root: Path, tmp_path: Path) -> None:
    skills_a = _skills_dir(tmp_path / "a")
    skills_b = _skills_dir(tmp_path / "b")
    mgr_a = _mgr(skills_a)
    try:
        ws_a = await mgr_a.acquire(Scope.SESSION, "sk-rb", "bot")
        # New manager (fresh registry) with a different source must rebuild the container
        # because config_hash now incorporates the skills source.
        mgr_b = _mgr(skills_b)
        ws_b = await mgr_b.acquire(Scope.SESSION, "sk-rb", "bot")
        assert ws_a != ws_b
    finally:
        await _cleanup(mgr_a, "sk-rb")
