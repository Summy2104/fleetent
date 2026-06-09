"""Unit tests for the workspace mount-path blocklist (sandbox-hardening, task 2)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from fleetent.integrations.sandbox.hardening import is_blocked_mount
from fleetent.integrations.sandbox.manager import SandboxManager, Scope


def test_ssh_dir_blocked() -> None:
    assert is_blocked_mount(Path.home() / ".ssh" / "ws") is True


def test_etc_blocked() -> None:
    assert is_blocked_mount("/etc/anything") is True


def test_root_home_blocked() -> None:
    assert is_blocked_mount("/root/x") is True


def test_normal_workspace_not_blocked(tmp_path) -> None:
    assert is_blocked_mount(tmp_path / "workspaces" / "sess") is False


def test_workspace_host_path_raises_on_blocked(monkeypatch) -> None:
    from fleetent import paths

    monkeypatch.setattr(paths, "workspaces_dir", lambda: Path.home() / ".ssh")
    mgr = SandboxManager(scope=Scope.SESSION)
    with pytest.raises(ValueError):
        mgr.workspace_host_path(Scope.SESSION, "sess", "bot")
    # must not have created anything under ~/.ssh
    assert not (Path.home() / ".ssh" / "sess").exists()


def test_workspace_host_path_ok_for_normal_dir(monkeypatch, tmp_path) -> None:
    from fleetent import paths

    monkeypatch.setattr(paths, "workspaces_dir", lambda: tmp_path / "workspaces")
    mgr = SandboxManager(scope=Scope.SESSION)
    p = mgr.workspace_host_path(Scope.SESSION, "sess", "bot")
    assert os.path.isdir(p)
