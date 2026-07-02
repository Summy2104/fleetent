"""Integration test: backflow PR sweep scheduler + config wiring (skill-backflow-git-pr).

Asserts the sweep interval default lands in SchedulingSettings and that
_build_platform_maintenance_scheduler registers the __skill_backflow_pr_sweep__ interval
job (injecting a scheduler so nothing actually starts).
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from fleetent import server
from fleetent.config import SchedulingSettings


def test_config_has_backflow_pr_sweep_interval() -> None:
    assert SchedulingSettings().skill_backflow_pr_sweep_interval_seconds == 120


def test_maintenance_scheduler_registers_backflow_sweep_job() -> None:
    sched = AsyncIOScheduler()
    result = server._build_platform_maintenance_scheduler(SchedulingSettings(), _scheduler=sched)
    assert result.get_job("__skill_backflow_pr_sweep__") is not None
