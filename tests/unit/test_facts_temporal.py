"""Unit tests: temporal-intent enum → concrete expiry boundary (code-computed)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fleetent.memory.facts_temporal import temporal_boundary


# A fixed reference instant: Thu 2026-06-25 04:53:17 UTC.
_NOW = datetime(2026, 6, 25, 4, 53, 17, tzinfo=UTC)


def test_none_returns_none() -> None:
    assert temporal_boundary("none", _NOW) is None


def test_unknown_returns_none() -> None:
    # Unrecognized intent is treated as no boundary (safe default).
    assert temporal_boundary("garbage", _NOW) is None


def test_today_is_end_of_today() -> None:
    b = temporal_boundary("today", _NOW)
    assert b == datetime(2026, 6, 25, 23, 59, 59, tzinfo=UTC)


def test_tomorrow_is_end_of_tomorrow() -> None:
    b = temporal_boundary("tomorrow", _NOW)
    assert b == datetime(2026, 6, 26, 23, 59, 59, tzinfo=UTC)


def test_this_week_is_end_of_sunday() -> None:
    # 2026-06-25 is a Thursday; the week's end (Sunday) is 2026-06-28.
    b = temporal_boundary("this_week", _NOW)
    assert b == datetime(2026, 6, 28, 23, 59, 59, tzinfo=UTC)


def test_this_month_is_last_day_of_month() -> None:
    b = temporal_boundary("this_month", _NOW)
    assert b == datetime(2026, 6, 30, 23, 59, 59, tzinfo=UTC)


def test_this_week_when_already_sunday() -> None:
    sunday = datetime(2026, 6, 28, 10, 0, 0, tzinfo=UTC)
    b = temporal_boundary("this_week", sunday)
    assert b == datetime(2026, 6, 28, 23, 59, 59, tzinfo=UTC)
