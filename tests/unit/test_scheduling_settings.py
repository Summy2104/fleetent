"""Unit tests for poll-engine SchedulingSettings fields."""

from __future__ import annotations

import fleetent.cron_scheduler as cs
from fleetent.config import SchedulingSettings


def test_scheduling_settings_defaults() -> None:
    s = SchedulingSettings()
    assert s.enabled is True
    assert s.default_timezone == "UTC"
    assert s.tick_interval_seconds == 10.0
    assert s.max_parallel == 4
    assert s.history_retention == 50


def test_scheduler_reads_poll_settings() -> None:
    s = SchedulingSettings(tick_interval_seconds=2.5, max_parallel=7, history_retention=11)
    sched = cs.CronScheduler(settings=s)
    assert sched._tick_interval == 2.5  # noqa: SLF001
    assert sched._max_parallel == 7  # noqa: SLF001
    assert sched._history_retention == 11  # noqa: SLF001
