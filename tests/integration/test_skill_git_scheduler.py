"""Integration test: SchedulingSettings field + platform maintenance scheduler wiring.

Asserts the inbound-sync interval default lands in SchedulingSettings and that
_build_platform_maintenance_scheduler registers the __skill_git_sync_sweep__ interval job
(injecting a scheduler so nothing actually starts).
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from fleetent import server
from fleetent.config import SchedulingSettings


def test_config_has_skill_git_sync_interval() -> None:
    assert SchedulingSettings().skill_git_sync_interval_seconds == 300


def test_maintenance_scheduler_registers_sync_job() -> None:
    sched = AsyncIOScheduler()
    result = server._build_platform_maintenance_scheduler(SchedulingSettings(), _scheduler=sched)
    assert result.get_job("__skill_git_sync_sweep__") is not None
