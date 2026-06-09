"""File-tools sandbox IO helper (file-tools-sandbox-execution).

Pure path resolution + shell-command builders for running the file tools inside
the sandbox container, locked to ``/workspace``. The async orchestration (acquire
container, client.exec) lives in the tools; everything here is pure string work so
it is unit-testable without docker.
"""

from __future__ import annotations

import posixpath
import shlex

# Container-side workspace mount point (matches sandbox-workspace-mount).
WORKSPACE = "/workspace"


def resolve_ws_path(path: str) -> str:
    """Resolve a tool path to a container-absolute path inside ``/workspace``.

    Relative paths resolve under ``/workspace``; absolute paths must already be
    inside it. Raises ``ValueError`` on any path that escapes ``/workspace`` after
    ``..`` normalization (so ``../etc/passwd``, ``/etc/passwd`` and the
    ``/workspace-evil`` look-alike are all rejected).
    """
    if path.startswith("/"):
        candidate = posixpath.normpath(path)
    else:
        candidate = posixpath.normpath(posixpath.join(WORKSPACE, path))
    if candidate != WORKSPACE and not candidate.startswith(WORKSPACE + "/"):
        raise ValueError(f"path escapes workspace: {path!r}")
    return candidate


def build_read_command(ws_path: str) -> str:
    """Read a file's full content (caller does pagination/binary detection)."""
    return f"cat -- {shlex.quote(ws_path)}"


def build_size_command(ws_path: str) -> str:
    """Byte size of a file (used to guard against reading huge/binary files)."""
    return f"wc -c -- {shlex.quote(ws_path)}"


def build_list_command(ws_path: str) -> str:
    """List a directory (one entry per line)."""
    return f"ls -1 -- {shlex.quote(ws_path)}"
