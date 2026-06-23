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


# ── host-degrade path fence (Task 2) ──────────────────────────────────────────


def test_resolve_host_relative_under_root(tmp_path) -> None:
    p = fsio.resolve_host_path(tmp_path, "a/b.txt")
    assert p == tmp_path / "a" / "b.txt"


def test_resolve_host_bare_relative_under_root(tmp_path) -> None:
    p = fsio.resolve_host_path(tmp_path, "out.txt")
    assert p == tmp_path / "out.txt"


def test_resolve_host_root_itself_ok(tmp_path) -> None:
    assert fsio.resolve_host_path(tmp_path, ".") == tmp_path


def test_resolve_host_traversal_rejected(tmp_path) -> None:
    with pytest.raises(ValueError):
        fsio.resolve_host_path(tmp_path, "../escape.txt")


def test_resolve_host_absolute_outside_rejected(tmp_path) -> None:
    with pytest.raises(ValueError):
        fsio.resolve_host_path(tmp_path, "/etc/passwd")


def test_resolve_host_prefix_lookalike_rejected(tmp_path) -> None:
    sibling = str(tmp_path) + "-evil"
    with pytest.raises(ValueError):
        fsio.resolve_host_path(tmp_path, sibling + "/x")


def test_resolve_host_workspace_abs_prefix_mapped_to_root(tmp_path) -> None:
    # The model lives in the container /workspace world and may pass /workspace/<rel>
    # absolute paths to host-side file tools (send_file, read/write).
    assert fsio.resolve_host_path(tmp_path, "/workspace/outbound/x.png") == (
        tmp_path / "outbound" / "x.png"
    )


def test_resolve_host_workspace_root_alone_maps_to_root(tmp_path) -> None:
    assert fsio.resolve_host_path(tmp_path, "/workspace") == tmp_path


def test_resolve_host_workspace_prefix_traversal_rejected(tmp_path) -> None:
    with pytest.raises(ValueError):
        fsio.resolve_host_path(tmp_path, "/workspace/../escape.txt")


def test_resolve_host_workspace_lookalike_not_mapped(tmp_path) -> None:
    # "/workspace-evil/..." must NOT be treated as the /workspace mount prefix.
    with pytest.raises(ValueError):
        fsio.resolve_host_path(tmp_path, "/workspace-evil/x")
