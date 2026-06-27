"""Build metadata helpers for deployment diagnostics."""

from __future__ import annotations

import os

from fleetent.structured_logging import get_logger

_BUILD_COMMIT_ENV = "FLEETENT_BUILD_COMMIT"
_UNKNOWN_COMMIT = "unknown"


def build_commit() -> str:
    """Return the build commit injected at image/build time."""
    value = os.environ.get(_BUILD_COMMIT_ENV, "").strip()
    return value or _UNKNOWN_COMMIT


def log_service_startup(service: str) -> None:
    """Record the service role and build commit at process startup."""
    get_logger("build").info(
        "service_startup",
        service=service,
        build_commit=build_commit(),
    )
