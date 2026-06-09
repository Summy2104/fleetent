"""Re-export shim — audit_log has moved to fleetent.audit_log (top-level base infra)."""

from fleetent.audit_log import (  # noqa: F401 — re-exports for callers still on old path
    DB_PATH,
    _init_db,
    _row_to_dict,
    search_audit,
    write_audit,
)

__all__ = ["write_audit", "search_audit", "DB_PATH"]
