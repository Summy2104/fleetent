"""Compatibility shim for governance quota."""

from fleetent.governance.quota import (
    DB_PATH,
    _get_quota,
    _get_usage,
    _init_db,
    check_quota,
    record_usage,
    set_quota,
)

__all__ = [
    "DB_PATH",
    "check_quota",
    "record_usage",
    "set_quota",
    "_get_quota",
    "_get_usage",
    "_init_db",
]
