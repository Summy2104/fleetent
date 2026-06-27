from __future__ import annotations

from datetime import datetime


def format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"expected datetime string, got {type(value).__name__}")


def parse_optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return parse_datetime(value)
