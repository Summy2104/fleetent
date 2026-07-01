"""Unit tests for cron_scheduler.compute_next_run (pure next-occurrence math)."""

from datetime import UTC, datetime, timedelta

from fleetent.cron_scheduler import compute_next_run


def test_interval_from_base():
    base = datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)
    now = base
    nxt = compute_next_run("interval", interval_seconds=60, base=base, now=now, tz="UTC")
    assert nxt == base + timedelta(seconds=60)


def test_interval_fast_forwards_past_now():
    # base far in the past (process was down); result must be the first FUTURE occurrence,
    # not a burst of missed slots.
    base = datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)
    now = datetime(2026, 7, 1, 0, 10, 30, tzinfo=UTC)  # 10.5 min later
    nxt = compute_next_run("interval", interval_seconds=60, base=base, now=now, tz="UTC")
    assert nxt > now
    assert nxt == datetime(2026, 7, 1, 0, 11, 0, tzinfo=UTC)


def test_interval_base_none_is_now_plus_interval():
    now = datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)
    nxt = compute_next_run("interval", interval_seconds=90, base=None, now=now, tz="UTC")
    assert nxt == now + timedelta(seconds=90)


def test_cron_next_weekday_morning():
    # Wed 2026-07-01 08:00 UTC → next "0 9 * * 1-5" fire is same day 09:00.
    now = datetime(2026, 7, 1, 8, 0, 0, tzinfo=UTC)
    nxt = compute_next_run("cron", cron_expr="0 9 * * 1-5", base=now, now=now, tz="UTC")
    assert nxt == datetime(2026, 7, 1, 9, 0, 0, tzinfo=UTC)


def test_cron_stale_base_still_returns_future():
    # base long in the past must not yield a past fire; cron result is strictly after now.
    base = datetime(2026, 6, 1, 9, 0, 0, tzinfo=UTC)
    now = datetime(2026, 7, 1, 8, 0, 0, tzinfo=UTC)
    nxt = compute_next_run("cron", cron_expr="0 9 * * 1-5", base=base, now=now, tz="UTC")
    assert nxt > now
    assert nxt == datetime(2026, 7, 1, 9, 0, 0, tzinfo=UTC)


def test_once_returns_fixed_run_at():
    run_at = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
    now = datetime(2026, 7, 1, 8, 0, 0, tzinfo=UTC)
    nxt = compute_next_run("once", run_at=run_at, base=None, now=now, tz="UTC")
    assert nxt == run_at
