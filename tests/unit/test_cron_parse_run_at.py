"""Unit: _parse_run_at robustness (cron-runat-hardening).

The one-shot run_at parser must tolerate common non-strict ISO forms the model emits
(a trailing ` UTC`/` GMT`/`Z`) in addition to strict ISO and relative durations, so a
human-ish timestamp can never become a reboot landmine. Pure parsing — no DB.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fleetent.cron_scheduler import _parse_run_at


def test_parse_run_at_utc_suffix():
    dt = _parse_run_at("2026-06-14 08:07:19 UTC")
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second) == (2026, 6, 14, 8, 7, 19)
    assert dt.utcoffset() == timedelta(0)


def test_parse_run_at_gmt_suffix():
    dt = _parse_run_at("2026-06-14 08:07:19 GMT")
    assert dt.utcoffset() == timedelta(0)


def test_parse_run_at_z_suffix():
    dt = _parse_run_at("2026-06-14T08:07:19Z")
    assert dt.utcoffset() == timedelta(0)
    assert dt.hour == 8


def test_parse_run_at_strict_iso_offset():
    dt = _parse_run_at("2026-06-14T08:07:19+00:00")
    assert dt.hour == 8 and dt.utcoffset() == timedelta(0)


def test_parse_run_at_relative_duration():
    before = datetime.now(UTC)
    dt = _parse_run_at("+30m")
    assert before <= dt <= before + timedelta(minutes=31)


def test_parse_run_at_unparseable_raises():
    with pytest.raises(ValueError):
        _parse_run_at("not a date at all")


# ── naive run_at is interpreted in the task timezone (fix-cron-store-and-once F3) ──


def test_parse_run_at_naive_uses_task_timezone():
    dt = _parse_run_at("2026-07-08 09:00", tz="Asia/Shanghai")
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute) == (2026, 7, 8, 9, 0)
    assert dt.utcoffset() == timedelta(hours=8)
    # Equivalent to 01:00 UTC — not 09:00 UTC (the pre-fix, host-timezone behavior).
    assert dt.astimezone(UTC).hour == 1


def test_parse_run_at_naive_defaults_to_utc_when_no_tz_given():
    dt = _parse_run_at("2026-07-08 09:00")
    assert dt.utcoffset() == timedelta(0)


def test_parse_run_at_explicit_offset_ignores_tz_param():
    """An input that already carries an explicit offset/Z/UTC/GMT suffix is never
    re-interpreted through `tz` — only a genuinely naive input is."""
    dt = _parse_run_at("2026-06-14T08:07:19+05:00", tz="Asia/Shanghai")
    assert dt.utcoffset() == timedelta(hours=5)


def test_parse_run_at_relative_duration_ignores_tz_param():
    before = datetime.now(UTC)
    dt = _parse_run_at("+30m", tz="Asia/Shanghai")
    assert before <= dt <= before + timedelta(minutes=31)
    assert dt.utcoffset() == timedelta(0)
