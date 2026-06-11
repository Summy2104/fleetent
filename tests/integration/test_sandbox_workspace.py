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
from fleetent.integrations.sandbox.manager import (
    SandboxManager,
    Scope,
    WorkspaceScope,
    _deps_image_tag,
)


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


# --- sandbox-workspace-scope-split: multi-user session isolation ------------


async def test_multi_user_same_agent_sessions_isolated(workspace_root: Path) -> None:
    """In a multi-user deployment, two sessions of the same agent acquire distinct,
    isolated containers + workspace dirs; one's /workspace write is invisible to the
    other (the old agent-scope shared-dir behaviour is gone)."""
    # multi_user forces workspace_scope=session even if agent were configured.
    mgr = SandboxManager(backend=SandboxClient(), scope=WorkspaceScope.AGENT, multi_user=True)
    assert mgr.scope is WorkspaceScope.SESSION
    try:
        ws_a = await mgr.acquire(WorkspaceScope.SESSION, session_id="userA", agent_name="bot")
        ws_b = await mgr.acquire(WorkspaceScope.SESSION, session_id="userB", agent_name="bot")
        assert ws_a != ws_b
        await mgr.backend.exec(ws_a, "echo A-private > /workspace/a.txt")
        result = await mgr.backend.exec(ws_b, "cat /workspace/a.txt")
        assert "A-private" not in result.stdout
        assert result.exit_code != 0
        host_a = workspace_root / "userA"
        host_b = workspace_root / "userB"
        assert host_a != host_b
    finally:
        await _cleanup(mgr, WorkspaceScope.SESSION, "userA", "bot")
        await _cleanup(mgr, WorkspaceScope.SESSION, "userB", "bot")


# --- sandbox-image-persistence: declarative immutable deps image ------------


async def test_declarative_deps_image_immutable_and_reused(workspace_root: Path) -> None:
    """An offline-built deps image carries the declared dependency and is reused on the
    next acquire; a container's write to its rootfs does NOT leak into the image, so a
    rebuilt container from the image carries only the declared deps, not prior writes."""
    tag = _deps_image_tag("itest-deps-agent")
    mgr = SandboxManager(
        backend=SandboxClient(),
        scope=WorkspaceScope.AGENT,
        image_persistence=True,
        setup_command="touch /opt/declared-dep",
    )
    try:
        # Offline build the immutable deps image from the declared setup_command.
        await mgr.backend.build_deps_image(
            image_tag=tag,
            setup_command="touch /opt/declared-dep",
            base_image="python:3.12-slim",
        )
        assert await mgr.backend.image_exists(tag)

        # Acquire boots from the deps image; declared dep is present.
        ws1 = await mgr.acquire(
            WorkspaceScope.AGENT, session_id="s1", agent_name="itest-deps-agent"
        )
        r1 = await mgr.backend.exec(ws1, "test -f /opt/declared-dep && echo yes")
        assert r1.stdout.strip() == "yes"
        # Write into the container rootfs (NOT into the immutable image).
        await mgr.backend.exec(ws1, "touch /opt/session-scribble")

        # Destroy + re-acquire from the same immutable image: the prior write is gone,
        # the declared dep remains (image immutability — no commit-from-running leak).
        name = mgr.container_name(WorkspaceScope.AGENT, "s1", "itest-deps-agent")
        await mgr.backend.destroy_workspace(name)
        mgr.forget(name)
        ws2 = await mgr.acquire(
            WorkspaceScope.AGENT, session_id="s1", agent_name="itest-deps-agent"
        )
        r_dep = await mgr.backend.exec(ws2, "test -f /opt/declared-dep && echo yes")
        assert r_dep.stdout.strip() == "yes"
        r_scribble = await mgr.backend.exec(
            ws2, "test -f /opt/session-scribble && echo leaked || echo clean"
        )
        assert r_scribble.stdout.strip() == "clean"
    finally:
        await _cleanup(mgr, WorkspaceScope.AGENT, "s1", "itest-deps-agent")
        subprocess.run(["docker", "image", "rm", "-f", tag], capture_output=True)


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
