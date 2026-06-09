"""Unit tests for file-tools sandbox IO helper (file-tools-sandbox-execution)."""

from __future__ import annotations

import pytest

from fleetent.tools import file_sandbox_io as fsio


def test_resolve_relative_under_workspace() -> None:
    assert fsio.resolve_ws_path("a/b.txt") == "/workspace/a/b.txt"


def test_resolve_bare_relative_under_workspace() -> None:
    assert fsio.resolve_ws_path("out.txt") == "/workspace/out.txt"


def test_resolve_absolute_inside_workspace_ok() -> None:
    assert fsio.resolve_ws_path("/workspace/a.txt") == "/workspace/a.txt"


def test_resolve_workspace_root_ok() -> None:
    assert fsio.resolve_ws_path("/workspace") == "/workspace"


def test_resolve_absolute_outside_rejected() -> None:
    with pytest.raises(ValueError):
        fsio.resolve_ws_path("/etc/passwd")


def test_resolve_traversal_rejected() -> None:
    with pytest.raises(ValueError):
        fsio.resolve_ws_path("../etc/passwd")


def test_resolve_traversal_via_subdir_rejected() -> None:
    with pytest.raises(ValueError):
        fsio.resolve_ws_path("a/../../etc/passwd")


def test_resolve_workspace_prefix_lookalike_rejected() -> None:
    # /workspace-evil must not be treated as inside /workspace
    with pytest.raises(ValueError):
        fsio.resolve_ws_path("/workspace-evil/x")


def test_build_read_command_quotes_path() -> None:
    cmd = fsio.build_read_command("/workspace/a b.txt")
    assert "cat" in cmd
    assert "'/workspace/a b.txt'" in cmd


def test_build_list_command_quotes_path() -> None:
    cmd = fsio.build_list_command("/workspace/a b")
    assert "ls" in cmd
    assert "'/workspace/a b'" in cmd
