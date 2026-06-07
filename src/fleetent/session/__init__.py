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
    clear_resume_pending,
    delete_compaction_checkpoint,
    enforce_capacity,
    externalize_tool_results,
    inject_message,
    is_expired,
    is_over_capacity,
    is_resume_pending,
    list_by_user,
    list_session_ids,
    load,
    load_meta,
    mark_resume_pending,
    maybe_run_maintenance,
    rehydrate_tool_results,
    reset,
    save,
    scan_and_mark_recent_resume,
    session_lock,
    start_session_maintenance,
    stop_session_maintenance,
    write_compaction_checkpoint,
)

__all__ = [
    "SESSIONS_DIR",
    "cleanup_expired",
    "clear",
    "clear_resume_pending",
    "delete_compaction_checkpoint",
    "write_compaction_checkpoint",
    "enforce_capacity",
    "externalize_tool_results",
    "inject_message",
    "is_expired",
    "is_resume_pending",
    "is_over_capacity",
    "list_by_user",
    "list_session_ids",
    "load",
    "load_meta",
    "mark_resume_pending",
    "maybe_run_maintenance",
    "rehydrate_tool_results",
    "scan_and_mark_recent_resume",
    "reset",
    "save",
    "session_lock",
    "start_session_maintenance",
    "stop_session_maintenance",
]
