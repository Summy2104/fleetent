"""File-tools sandbox IO helper (file-tools-sandbox-execution).

Pure path resolution + shell-command builders for running the file tools inside
the sandbox container, locked to ``/workspace``. The async orchestration (acquire
container, client.exec) lives in the tools; everything here is pure string work so
it is unit-testable without docker.
"""

from __future__ import annotations

import os
import posixpath
import shlex
from pathlib import Path

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


def build_probe_command(ws_path: str) -> str:
    """Classify a path inside the container: ``dir`` / ``file <bytes>`` / ``other`` / ``missing``.

    A single test cascade so existence, type and size come back in one exec.
    """
    q = shlex.quote(ws_path)
    return (
        f"if [ -d {q} ]; then echo dir; "
        f'elif [ -f {q} ]; then echo "file $(wc -c < {q})"; '
        f"elif [ -e {q} ]; then echo other; "
        f"else echo missing; fi"
    )


def build_read_b64_command(ws_path: str) -> str:
    """Read a file as base64 so arbitrary bytes survive the text exec channel.

    The host decodes the base64 back to bytes, then runs binary detection / decoding —
    keeping the functional logic on the host (design D3) while the IO stays in-container.
    """
    return f"base64 -- {shlex.quote(ws_path)}"


def build_listdir_command(ws_path: str) -> str:
    r"""List a directory with per-entry type/size/mtime for the host to format.

    ``find -printf`` emits ``name\ttype\tsize\tmtime`` per entry (type ``d`` for dirs);
    the host reconstructs the mtime-sorted listing that the non-sandbox tool produced.
    """
    q = shlex.quote(ws_path)
    return f"find {q} -maxdepth 1 -mindepth 1 -printf '%f\\t%y\\t%s\\t%T@\\n'"


def build_write_command(ws_path: str) -> str:
    """Overwrite a file with content streamed on stdin (``cat >``), creating parents.

    The payload travels via ``docker exec -i`` stdin (not argv), so size is bounded by
    the file system, not ARG_MAX. ``cat`` writes the bytes verbatim — no added newline.
    """
    q = shlex.quote(ws_path)
    return f'mkdir -p -- "$(dirname -- {q})" && cat > {q}'


def build_grep_command(pattern: str, ws_path: str, include: str, max_results: int) -> str:
    """Recursive content search inside the workspace via ``grep`` (container default).

    ``-r`` recurse, ``-n`` line numbers, ``-I`` skip binary, ``-E`` extended regex.
    An ``include`` glob maps to ``--include``. The search root is the resolved workspace
    path, so matches can never escape ``/workspace``. ``-m`` caps matches per file to keep
    output bounded; the host applies the final cross-file truncation.
    """
    parts = ["grep", "-rnI", "-E", f"-m{int(max_results)}"]
    if include:
        parts.append(f"--include={shlex.quote(include)}")
    parts += ["-e", shlex.quote(pattern), "--", shlex.quote(ws_path)]
    return " ".join(parts)


def build_find_command(pattern: str, ws_path: str) -> str:
    r"""Find files by name glob inside the workspace, sorted by mtime (newest first).

    ``find -name`` matches the basename, so a recursive glob like ``**/*.py`` collapses
    to its trailing component. ``-printf '%T@\t%p'`` + ``sort -rn`` reproduces the
    mtime-descending order the non-sandbox tool returned; ``cut`` drops the sort key.
    """
    name = posixpath.basename(pattern) or pattern
    q = shlex.quote(ws_path)
    n = shlex.quote(name)
    return f"find {q} -type f -name {n} -printf '%T@\\t%p\\n' | sort -rn | cut -f2-"


def resolve_host_path(root: Path, path: str) -> Path:
    """Resolve a tool path inside the host workspace dir (docker-unavailable degrade).

    Mirrors :func:`resolve_ws_path` but for the host fallback: ``root`` is the host
    directory that *would* be mounted at ``/workspace``. Relative paths resolve under
    ``root``; absolute paths must already be inside it. Uses ``normpath`` (not
    ``realpath``) — ``..`` is rejected, but symlinks are NOT followed, so this fence
    stops direct path attacks (the prompt-injection main case) and accepts the
    symlink/TOCTOU gap documented in the design (no mount namespace without docker).
    """
    base = os.path.normpath(str(root))
    if os.path.isabs(path):
        candidate = os.path.normpath(path)
    else:
        candidate = os.path.normpath(os.path.join(base, path))
    if candidate != base and not candidate.startswith(base + os.sep):
        raise ValueError(f"path escapes workspace: {path!r}")
    return Path(candidate)
