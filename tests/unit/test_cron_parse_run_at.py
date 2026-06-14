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
