"""Workspace host-directory garbage collection (sandbox-workspace-gc).

Reclaims the host workspace directories bind-mounted into sandbox containers, which
were never collected by the session-TTL pipeline (it only touched ``SESSIONS_DIR``),
leaving sensitive uploads lingering and agent-scope dirs growing unbounded.

Two scope strategies:

- ``session`` scope: on session TTL expiry the whole per-session workspace dir is
  ``rmtree``'d (container destroyed first by the existing release path). A session is
  truly terminal at TTL expiry, so the whole dir — uploads and generated artefacts —
  goes.
- ``agent`` scope: multiple sessions share one agent dir, so it MUST NOT be deleted
  wholesale; instead its entries are pruned by mtime, keeping recent content and the
  dir itself.

Every deletion is fenced twice — the workspace-creation-source ``is_blocked_mount``
guard plus a realpath-inside-``workspaces``-root check — so GC never deletes outside
the workspace root or under a sensitive host path, even via a symlink escape. No
platform imports; both callers (session TTL cleanup, idle sweep) reach this via the
sandbox public API rather than the manager internals.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from fleetent import paths
from fleetent.integrations.sandbox.hardening import is_blocked_mount
from fleetent.integrations.sandbox.manager import _name_key
from fleetent.structured_logging import get_logger

_logger = get_logger("sandbox.workspace_gc")

# Default agent-scope retention: entries untouched for longer than this are pruned.
# Conservative (24h) so cross-session reused deps are not reaped mid-use; agent-scope
# data-isolation tightening is a later scope-split change, this is bounded止血.
_DEFAULT_AGENT_RETENTION_SECONDS = 86_400.0


def _session_dir_for(session_id: str) -> Path:
    """The session-scope workspace dir for ``session_id`` (collision-free key)."""
    return paths.workspaces_dir() / _name_key(session_id)


def _agent_dir_for(agent_name: str) -> Path:
    """The agent-scope workspace dir for ``agent_name`` (collision-free key)."""
    return paths.workspaces_dir() / _name_key(agent_name)


def _guarded(path: Path) -> bool:
    """Whether ``path`` is safe to delete: in-root (realpath) and not blocked.

    Both checks use realpath so a symlink cannot point the deletion at a target
    outside the ``workspaces`` root or under a sensitive host area.
    """
    if is_blocked_mount(path):
        _logger.warn("workspace_gc_blocked_mount_refused", path=str(path))
        return False
    root_real = os.path.realpath(str(paths.workspaces_dir()))
    target_real = os.path.realpath(str(path))
    if target_real != root_real and not target_real.startswith(root_real + os.sep):
        _logger.warn("workspace_gc_outside_root_refused", path=str(path), root=root_real)
        return False
    return True


def gc_session_workspace(session_id: str) -> bool:
    """Reclaim a session's workspace dir entirely (called on session TTL expiry).

    The session-scope container MUST already have been released by the caller's
    existing release path before this runs, so no live bind mount is removed underneath
    a running container. Idempotent: a missing dir is a no-op.

    Args:
        session_id: The expired session's id.

    Returns:
        True when a directory was removed, False when absent or guard-rejected.
    """
    target = _session_dir_for(session_id)
    if not target.exists():
        return False
    if not _guarded(target):
        return False
    shutil.rmtree(target, ignore_errors=True)
    _logger.info("workspace_gc_session_reclaimed", session_id=session_id, path=str(target))
    return True


def gc_agent_workspace(
    agent_name: str,
    *,
    retention_seconds: float = _DEFAULT_AGENT_RETENTION_SECONDS,
    _now: float | None = None,
) -> int:
    """Prune stale entries inside an agent-scope workspace dir (never the dir itself).

    Each top-level entry whose mtime is older than ``retention_seconds`` is removed;
    recent entries and the directory itself are kept (agent dirs are cross-session
    shared, so a wholesale delete would reap in-use deps). The dir is guard-checked
    once; each entry is guard-checked before removal so a symlinked entry cannot
    escape the root.

    Args:
        agent_name: The agent whose workspace dir is pruned.
        retention_seconds: Max idle age (by mtime) before an entry is pruned.
        _now: Override for the current time (testing); defaults to ``time.time()``.

    Returns:
        The number of top-level entries removed.
    """
    target = _agent_dir_for(agent_name)
    if not target.is_dir():
        return 0
    if not _guarded(target):
        return 0
    now = time.time() if _now is None else _now
    removed = 0
    for entry in target.iterdir():
        try:
            age = now - entry.stat().st_mtime
        except OSError as exc:
            _logger.warn("workspace_gc_stat_failed", path=str(entry), error=str(exc))
            continue
        if age <= retention_seconds:
            continue
        if not _guarded(entry):
            continue
        try:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink()
        except OSError as exc:
            _logger.warn("workspace_gc_entry_delete_failed", path=str(entry), error=str(exc))
            continue
        removed += 1
    if removed:
        _logger.info("workspace_gc_agent_pruned", agent_name=agent_name, removed=removed)
    return removed
