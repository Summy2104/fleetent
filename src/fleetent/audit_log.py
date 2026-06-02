"""Compatibility shim for governance audit log."""

from fleetent.governance.audit_log import DB_PATH, _init_db, search_audit, write_audit

__all__ = ["DB_PATH", "search_audit", "write_audit", "_init_db"]
