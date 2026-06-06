"""Session capability public API.

Per-session transcript persistence: atomic JSON read/write, per-session locks,
TTL/LRU maintenance, and a lightweight metadata index. Cross-package callers
import from here (or ``from fleetent.session import manager as session_mgr``),
not from the internal modules. ``index`` stays package-internal — only
``manager`` references it.
"""

from fleetent.session.manager import (
    SESSIONS_DIR,
    cleanup_expired,
    clear,
    delete_compaction_checkpoint,
    enforce_capacity,
    inject_message,
    is_expired,
    is_over_capacity,
    list_by_user,
    list_session_ids,
    load,
    load_meta,
    maybe_run_maintenance,
    reset,
    save,
    session_lock,
    start_session_maintenance,
    stop_session_maintenance,
    write_compaction_checkpoint,
)

__all__ = [
    "SESSIONS_DIR",
    "cleanup_expired",
    "clear",
    "delete_compaction_checkpoint",
    "write_compaction_checkpoint",
    "enforce_capacity",
    "inject_message",
    "is_expired",
    "is_over_capacity",
    "list_by_user",
    "list_session_ids",
    "load",
    "load_meta",
    "maybe_run_maintenance",
    "reset",
    "save",
    "session_lock",
    "start_session_maintenance",
    "stop_session_maintenance",
]
