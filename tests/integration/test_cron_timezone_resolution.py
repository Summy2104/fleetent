"""Timezone resolution for tool-created scheduled tasks: precedence
explicit > agent.scheduling.default_timezone > UTC, with cron fields read as
local wall-clock (no UTC pre-conversion)."""

from __future__ import annotations

import fleetent.cron_scheduler as cs
import fleetent.schedule_store as store
from fleetent.config import SchedulingSettings
from fleetent.tools import builtin_tools


def _only_task_id() -> str:
    tasks = store.list_tasks()
    assert len(tasks) == 1, f"expected exactly one task, got {len(tasks)}"
    return str(tasks[0]["id"])


async def test_tool_create_without_timezone_uses_deployment_default(isolated_schedule_db):
    """No timezone supplied → the deployment default applies (not a hardcoded UTC)."""
    scheduler = cs.CronScheduler(settings=SchedulingSettings(default_timezone="Asia/Shanghai"))
    await scheduler.start()
    try:
        await builtin_tools.schedule(
            action="create",
            name="kb-pull",
            schedule_kind="cron",
            cron_expr="0 18 * * *",
            message="拉取知识库文档列表",
        )
        job = scheduler.get_job(_only_task_id())
        assert job is not None
        assert str(job.trigger.timezone) == "Asia/Shanghai"
    finally:
        await scheduler.shutdown()


async def test_tool_create_cron_is_local_wall_clock(isolated_schedule_db):
    """cron '0 18' + Asia/Shanghai fires at local 18:00 — not 18:00 UTC, not 10:00 local."""
    scheduler = cs.CronScheduler(settings=SchedulingSettings(default_timezone="UTC"))
    await scheduler.start()
    try:
        await builtin_tools.schedule(
            action="create",
            name="kb-pull",
            schedule_kind="cron",
            cron_expr="0 18 * * *",
            message="拉取知识库文档列表",
            timezone="Asia/Shanghai",
        )
        job = scheduler.get_job(_only_task_id())
        assert job is not None
        assert str(job.trigger.timezone) == "Asia/Shanghai"
        assert job.next_run_time.hour == 18  # local wall-clock, not pre-converted to UTC
    finally:
        await scheduler.shutdown()


async def test_tool_create_explicit_timezone_overrides_default(isolated_schedule_db):
    """An explicit per-task timezone wins over the deployment default."""
    scheduler = cs.CronScheduler(settings=SchedulingSettings(default_timezone="Asia/Shanghai"))
    await scheduler.start()
    try:
        await builtin_tools.schedule(
            action="create",
            name="ny",
            schedule_kind="cron",
            cron_expr="0 9 * * *",
            message="x",
            timezone="America/New_York",
        )
        job = scheduler.get_job(_only_task_id())
        assert job is not None
        assert str(job.trigger.timezone) == "America/New_York"
    finally:
        await scheduler.shutdown()
