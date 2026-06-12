"""Unit tests: workspace relative-path resolution invariant (sandbox-workspace-root).

Pure string/path resolution — `resolve_ws_path` (container, rooted at /workspace) and
`resolve_host_path` (host fence) resolve the SAME relative path to the SAME logical
location under their respective roots, and both reject workspace escapes. No docker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent.tools.file_sandbox_io import WORKSPACE, resolve_host_path, resolve_ws_path


def test_relative_resolves_under_workspace() -> None:
    assert resolve_ws_path("sub/a.txt") == f"{WORKSPACE}/sub/a.txt"


def test_generated_relative_resolves_under_workspace() -> None:
    assert resolve_ws_path("generated/x.png") == f"{WORKSPACE}/generated/x.png"


def test_uploads_relative_resolves_under_workspace() -> None:
    assert resolve_ws_path("uploads/a.png") == f"{WORKSPACE}/uploads/a.png"


@pytest.mark.parametrize("bad", ["/etc/passwd", "../../etc/passwd", "../escape"])
def test_escape_rejected_in_container(bad: str) -> None:
    with pytest.raises(ValueError, match="escape"):
        resolve_ws_path(bad)


def test_host_resolves_same_relative_under_root(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    # Same relative path the container would see resolves under the host root.
    assert resolve_host_path(root, "sub/a.txt") == root / "sub" / "a.txt"
    assert resolve_host_path(root, "generated/x.png") == root / "generated" / "x.png"


@pytest.mark.parametrize("bad", ["/etc/passwd", "../../etc/passwd", "../escape"])
def test_escape_rejected_on_host(tmp_path: Path, bad: str) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    with pytest.raises(ValueError, match="escape"):
        resolve_host_path(root, bad)


def test_same_relative_maps_consistently(tmp_path: Path) -> None:
    # The container path's tail (relative to /workspace) equals the host path's tail
    # (relative to root) — the single-physical-file invariant on one relative path.
    root = tmp_path / "ws"
    root.mkdir()
    rel = "out/r.txt"
    container = resolve_ws_path(rel)
    host = resolve_host_path(root, rel)
    container_tail = container[len(WORKSPACE) + 1 :]
    host_tail = str(host.relative_to(root))
    assert container_tail == host_tail == rel
