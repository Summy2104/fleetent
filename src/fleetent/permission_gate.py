"""Compatibility shim for governance permission gate."""

from fleetent.governance.permission_gate import (
    DB_PATH,
    ApprovalResult,
    PermissionGate,
    _default_gate,
    _init_db,
    cleanup_stale_approvals,
    list_approvals,
)

__all__ = [
    "ApprovalResult",
    "PermissionGate",
    "_default_gate",
    "cleanup_stale_approvals",
    "list_approvals",
    "_init_db",
    "DB_PATH",
]
