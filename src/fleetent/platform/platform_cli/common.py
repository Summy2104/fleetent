"""Shared helpers for the platform CLI."""

import sys
from collections.abc import Mapping
from datetime import datetime


def sanitize_cli_value(value: object) -> str:
    """Return a CLI-safe string with secrets redacted."""
    from fleetent.knowledge_base.operations import _sanitize_text
    from fleetent.structured_logging import _redact_value

    return _sanitize_text(str(_redact_value(value)))


def summary_line(summary: Mapping[str, object]) -> str:
    """Format a sorted key=value summary line."""
    return " ".join(f"{key}={sanitize_cli_value(value)}" for key, value in sorted(summary.items()))


def parse_iso_time(value: str | None, flag: str) -> datetime | None:
    """Parse an ISO timestamp or terminate with the legacy CLI error format."""
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        print(f"invalid timestamp for {flag}: {value}", file=sys.stderr)
        sys.exit(1)


def format_optional(value: str | None) -> str:
    """Format an optional field for table output."""
    return value or "-"


def payload_keys(payload: Mapping[str, object]) -> str:
    """Format redacted payload key names for trace table output."""
    keys = sorted(str(key) for key in payload)[:8]
    return ",".join(keys) if keys else "-"
