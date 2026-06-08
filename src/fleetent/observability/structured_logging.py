"""Backwards-compatible shim for the relocated structured_logging module.

The structured logger moved to the top-level infrastructure module
``fleetent.structured_logging``. This shim re-exports its public and
already-consumed names so existing imports keep working during the migration
window; it is removed once all callers move to the new path.
"""

from __future__ import annotations

from fleetent.structured_logging import *  # noqa: F401,F403
from fleetent.structured_logging import (
    Logger,
    _redact_value,
    configure_structured_logging,
    get_logger,
)

__all__ = [
    "Logger",
    "configure_structured_logging",
    "get_logger",
    "_redact_value",
]
