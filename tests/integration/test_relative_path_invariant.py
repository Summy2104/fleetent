"""Integration: relative-path invariant across container & host-degrade modes.

Skipped when docker is unavailable. Container mode writes a relative path; host-fence
mode reads the same relative path from the same per-scope workspace dir, and vice
versa — proving both modes resolve one relative path to one physical file
(sandbox-workspace-root).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from fleetent import paths
from fleetent.integrations.sandbox.client import SandboxClient
from fleetent.integrations.sandbox.manager import SandboxManager, Scope
from fleetent.tools.file_sandbox_io import resolve_host_path


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


async def test_container_write_host_read_same_file(workspace_root: Path) -> None:
    mgr = SandboxManager(backend=SandboxClient(), scope=Scope.SESSION)
    try:
        ws = await mgr.acquire(Scope.SESSION, "inv-sess", "bot")
        await mgr.backend.exec(ws, "echo container-bytes > /workspace/data.txt")
        # Host-degrade reads the same relative path under the per-scope workspace dir.
        host_root = mgr.workspace_host_path(Scope.SESSION, "inv-sess", "bot")
        host_file = resolve_host_path(host_root, "data.txt")
        assert host_file.read_text().strip() == "container-bytes"
    finally:
        await mgr.backend.destroy_workspace(mgr.container_name(Scope.SESSION, "inv-sess", "bot"))


async def test_host_write_container_read_same_file(workspace_root: Path) -> None:
    mgr = SandboxManager(backend=SandboxClient(), scope=Scope.SESSION)
    try:
        # Host-degrade writes a relative path first.
        host_root = mgr.workspace_host_path(Scope.SESSION, "inv-sess2", "bot")
        host_file = resolve_host_path(host_root, "out/r.txt")
        host_file.parent.mkdir(parents=True, exist_ok=True)
        host_file.write_text("host-bytes")
        # Container reads the same relative path at /workspace/out/r.txt.
        ws = await mgr.acquire(Scope.SESSION, "inv-sess2", "bot")
        res = await mgr.backend.exec(ws, "cat /workspace/out/r.txt")
        assert res.stdout.strip() == "host-bytes"
    finally:
        await mgr.backend.destroy_workspace(mgr.container_name(Scope.SESSION, "inv-sess2", "bot"))
