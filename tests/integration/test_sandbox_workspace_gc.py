"""Integration: workspace GC real filesystem reclamation (sandbox-workspace-gc).

Real ``tmp_path`` workspace dirs (no docker needed — GC is filesystem-only): a
session-scope dir is removed wholesale, an agent-scope dir keeps recent content and
the dir itself while pruning stale-by-mtime entries, and a guard rejects an
out-of-root target without touching the filesystem.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent import paths
from fleetent.integrations.sandbox import gc_agent_workspace, gc_session_workspace
from fleetent.integrations.sandbox.manager import _name_key


@pytest.fixture
def workspace_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "workspaces"
    root.mkdir()
    monkeypatch.setattr(paths, "workspaces_dir", lambda: root)
    return root


def test_session_workspace_reclaimed_wholesale(workspace_root: Path) -> None:
    """An expired session's whole workspace dir (uploads + artefacts) is removed."""
    session_id = "user:U1/chan#a"
    sess_dir = workspace_root / _name_key(session_id)
    (sess_dir / "uploads").mkdir(parents=True)
    (sess_dir / "uploads" / "salary.xlsx").write_text("secret")
    (sess_dir / "out.txt").write_text("artefact")

    assert gc_session_workspace(session_id) is True
    assert not sess_dir.exists()


def test_session_gc_missing_dir_is_noop(workspace_root: Path) -> None:
    assert gc_session_workspace("never-existed") is False


def test_agent_workspace_prunes_only_stale(workspace_root: Path) -> None:
    """Agent dir keeps recent content + the dir itself; only stale-by-mtime pruned."""
    agent = "my-agent"
    agent_dir = workspace_root / _name_key(agent)
    agent_dir.mkdir()
    stale = agent_dir / "old.bin"
    stale.write_text("old")
    recent = agent_dir / "fresh.bin"
    recent.write_text("new")

    now = 1_000_000.0
    import os

    os.utime(stale, (now - 100_000, now - 100_000))  # well past retention
    os.utime(recent, (now - 10, now - 10))  # recent

    removed = gc_agent_workspace(agent, retention_seconds=3600.0, _now=now)

    assert removed == 1
    assert not stale.exists()
    assert recent.exists()
    assert agent_dir.is_dir()  # the dir itself is never removed


def test_agent_gc_keeps_everything_when_recent(workspace_root: Path) -> None:
    agent = "agent-b"
    agent_dir = workspace_root / _name_key(agent)
    agent_dir.mkdir()
    f = agent_dir / "data"
    f.write_text("x")
    now = 1_000_000.0
    import os

    os.utime(f, (now - 5, now - 5))
    assert gc_agent_workspace(agent, retention_seconds=3600.0, _now=now) == 0
    assert f.exists()


def test_gc_refuses_outside_root_via_symlink(workspace_root: Path, tmp_path: Path) -> None:
    """A session dir that is actually a symlink to outside the root is not deleted."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("must survive")
    session_id = "escapee"
    link = workspace_root / _name_key(session_id)
    link.symlink_to(outside)

    assert gc_session_workspace(session_id) is False
    assert (outside / "keep.txt").exists()
