"""Unit tests for workspace GC pure logic (sandbox-workspace-gc).

Covers the deletion-decision guardrails (``_guarded``) and the scope→derived-dir
mapping without performing real filesystem deletion (that is the integration layer's
job): a path that resolves outside the ``workspaces`` root or hits a sensitive
``is_blocked_mount`` root MUST be rejected; a normal in-root path is accepted.
"""

from __future__ import annotations

from pathlib import Path

from fleetent.integrations.sandbox import workspace_gc


def test_guarded_accepts_path_inside_workspaces_root(monkeypatch, tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    monkeypatch.setattr(workspace_gc.paths, "workspaces_dir", lambda: root)
    target = root / "some-session"
    target.mkdir()
    assert workspace_gc._guarded(target) is True


def test_guarded_rejects_path_outside_workspaces_root(monkeypatch, tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    monkeypatch.setattr(workspace_gc.paths, "workspaces_dir", lambda: root)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    assert workspace_gc._guarded(outside) is False


def test_guarded_rejects_symlink_escape(monkeypatch, tmp_path):
    """A symlink inside the root pointing outside resolves (realpath) out of root."""
    root = tmp_path / "workspaces"
    root.mkdir()
    monkeypatch.setattr(workspace_gc.paths, "workspaces_dir", lambda: root)
    outside = tmp_path / "secret"
    outside.mkdir()
    link = root / "escape"
    link.symlink_to(outside)
    assert workspace_gc._guarded(link) is False


def test_guarded_rejects_blocked_mount(monkeypatch, tmp_path):
    """A path hitting is_blocked_mount (sensitive root) is rejected even if the
    realpath-in-root check would otherwise pass."""
    root = tmp_path / "workspaces"
    root.mkdir()
    monkeypatch.setattr(workspace_gc.paths, "workspaces_dir", lambda: root)
    target = root / "x"
    target.mkdir()
    monkeypatch.setattr(workspace_gc, "is_blocked_mount", lambda p: True)
    assert workspace_gc._guarded(target) is False


def test_session_dir_for_derives_name_key(monkeypatch, tmp_path):
    """The session-scope dir is keyed by the collision-free _name_key of session_id."""
    root = tmp_path / "workspaces"
    monkeypatch.setattr(workspace_gc.paths, "workspaces_dir", lambda: root)
    from fleetent.integrations.sandbox.manager import _name_key

    session_id = "user:U1/chan#a"
    assert workspace_gc._session_dir_for(session_id) == root / _name_key(session_id)


def test_agent_dir_for_derives_name_key(monkeypatch, tmp_path):
    root = tmp_path / "workspaces"
    monkeypatch.setattr(workspace_gc.paths, "workspaces_dir", lambda: root)
    from fleetent.integrations.sandbox.manager import _name_key

    agent = "my:agent/x"
    assert workspace_gc._agent_dir_for(agent) == root / _name_key(agent)


def test_session_dir_and_agent_dir_distinct_for_long_same_prefix(monkeypatch, tmp_path):
    """Long same-prefix keys map to distinct dirs (collision-free, mirrors manager)."""
    root = tmp_path / "workspaces"
    monkeypatch.setattr(workspace_gc.paths, "workspaces_dir", lambda: root)
    prefix = "k" * 60
    a = workspace_gc._session_dir_for(prefix + "-A")
    b = workspace_gc._session_dir_for(prefix + "-B")
    assert a != b
    assert isinstance(a, Path)
