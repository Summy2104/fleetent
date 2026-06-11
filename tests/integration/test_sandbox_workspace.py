"""Integration tests for sandbox workspace bind mount (real docker).

Skipped when docker is unavailable. Establishes the docker-availability skip
guard pattern for sandbox integration tests (prior sandbox tests are all unit +
mock).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from fleetent import paths
from fleetent.integrations.sandbox.client import SandboxClient
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


async def _cleanup(mgr: SandboxManager, scope: Scope, session_id: str, agent_name: str) -> None:
    await mgr.backend.destroy_workspace(mgr.container_name(scope, session_id, agent_name))


async def test_session_tier_writes_to_host_workspace(workspace_root: Path) -> None:
    """A session-tier (nobody, read-only rootfs) container can write /workspace, and
    the write is visible on the host workspace dir (mount + uid write perm work)."""
    mgr = SandboxManager(backend=SandboxClient(), scope=Scope.SESSION)
    try:
        ws_id = await mgr.acquire(Scope.SESSION, session_id="itest-sess", agent_name="bot")
        await mgr.backend.exec(ws_id, "echo hello > /workspace/out.txt")
        host_file = workspace_root / "itest-sess" / "out.txt"
        assert host_file.exists()
        assert host_file.read_text().strip() == "hello"
    finally:
        await _cleanup(mgr, Scope.SESSION, "itest-sess", "bot")


async def test_agent_tier_writes_to_host_workspace(workspace_root: Path) -> None:
    """An agent-tier (root, writable) container can also write /workspace to host."""
    mgr = SandboxManager(backend=SandboxClient(), scope=Scope.AGENT)
    try:
        ws_id = await mgr.acquire(Scope.AGENT, session_id="s1", agent_name="itest-agent")
        await mgr.backend.exec(ws_id, "echo world > /workspace/out.txt")
        host_file = workspace_root / "itest-agent" / "out.txt"
        assert host_file.exists()
        assert host_file.read_text().strip() == "world"
    finally:
        await _cleanup(mgr, Scope.AGENT, "s1", "itest-agent")


async def test_workspace_persists_across_container_destroy(workspace_root: Path) -> None:
    """Destroying the container does not delete the host workspace; a re-acquired
    container sees the prior content."""
    mgr = SandboxManager(backend=SandboxClient(), scope=Scope.SESSION)
    try:
        ws_id = await mgr.acquire(Scope.SESSION, session_id="itest-persist", agent_name="bot")
        await mgr.backend.exec(ws_id, "echo keep > /workspace/state.txt")
        await mgr.backend.destroy_workspace(
            mgr.container_name(Scope.SESSION, "itest-persist", "bot")
        )
        mgr.forget(mgr.container_name(Scope.SESSION, "itest-persist", "bot"))
        ws_id2 = await mgr.acquire(Scope.SESSION, session_id="itest-persist", agent_name="bot")
        result = await mgr.backend.exec(ws_id2, "cat /workspace/state.txt")
        assert result.stdout.strip() == "keep"
    finally:
        await _cleanup(mgr, Scope.SESSION, "itest-persist", "bot")


async def test_host_path_outside_workspace_not_reachable(
    workspace_root: Path, tmp_path: Path
) -> None:
    """A host file outside the workspace mount is not reachable inside the container
    (mount namespace boundary)."""
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET")
    mgr = SandboxManager(backend=SandboxClient(), scope=Scope.SESSION)
    try:
        ws_id = await mgr.acquire(Scope.SESSION, session_id="itest-sec", agent_name="bot")
        result = await mgr.backend.exec(ws_id, f"cat {secret}")
        assert "TOP-SECRET" not in result.stdout
        assert result.exit_code != 0
    finally:
        await _cleanup(mgr, Scope.SESSION, "itest-sec", "bot")


async def test_same_prefix_long_keys_isolated_containers_and_workspaces(
    workspace_root: Path,
) -> None:
    """Two session keys sharing a >budget prefix but differing only in the truncated
    tail acquire distinct containers and distinct host workspaces — one's write to
    /workspace is invisible to the other's container (no collision)."""
    prefix = "u" * 60  # past the 47-char name-key budget
    key_a = prefix + "-AAAA"
    key_b = prefix + "-BBBB"
    mgr = SandboxManager(backend=SandboxClient(), scope=Scope.SESSION)
    try:
        name_a = mgr.container_name(Scope.SESSION, key_a, "bot")
        name_b = mgr.container_name(Scope.SESSION, key_b, "bot")
        assert name_a != name_b

        ws_a = await mgr.acquire(Scope.SESSION, session_id=key_a, agent_name="bot")
        ws_b = await mgr.acquire(Scope.SESSION, session_id=key_b, agent_name="bot")
        assert ws_a != ws_b

        await mgr.backend.exec(ws_a, "echo from-A > /workspace/owner.txt")
        # B's container must not see A's file (distinct host workspace dir mounted).
        result = await mgr.backend.exec(ws_b, "cat /workspace/owner.txt")
        assert "from-A" not in result.stdout
        assert result.exit_code != 0

        host_a = workspace_root / mgr.workspace_host_path(Scope.SESSION, key_a, "bot").name
        host_b = workspace_root / mgr.workspace_host_path(Scope.SESSION, key_b, "bot").name
        assert host_a != host_b
    finally:
        await _cleanup(mgr, Scope.SESSION, key_a, "bot")
        await _cleanup(mgr, Scope.SESSION, key_b, "bot")


async def test_session_snapshot_env_continuity(workspace_root: Path) -> None:
    """An exported var set in one session exec is visible in the next (snapshot)."""
    mgr = SandboxManager(backend=SandboxClient(), scope=Scope.SESSION)
    sess = "itest-snap-env"
    try:
        ws_id = await mgr.acquire(Scope.SESSION, session_id=sess, agent_name="bot")
        await mgr.backend.exec(ws_id, "export FOO=bar", session_id=sess)
        result = await mgr.backend.exec(ws_id, "echo $FOO", session_id=sess)
        assert result.stdout.strip() == "bar"
    finally:
        await _cleanup(mgr, Scope.SESSION, sess, "bot")


async def test_session_snapshot_cwd_continuity(workspace_root: Path) -> None:
    """A cd in one session exec persists to the next (cwd marker)."""
    mgr = SandboxManager(backend=SandboxClient(), scope=Scope.SESSION)
    sess = "itest-snap-cwd"
    try:
        ws_id = await mgr.acquire(Scope.SESSION, session_id=sess, agent_name="bot")
        await mgr.backend.exec(ws_id, "mkdir -p /workspace/sub", session_id=sess)
        await mgr.backend.exec(ws_id, "cd /workspace/sub", session_id=sess)
        result = await mgr.backend.exec(ws_id, "pwd", session_id=sess)
        assert result.stdout.strip() == "/workspace/sub"
    finally:
        await _cleanup(mgr, Scope.SESSION, sess, "bot")
