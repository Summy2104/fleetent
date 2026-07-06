"""Timezone resolution for tool-created scheduled tasks: precedence
explicit > agent.scheduling.default_timezone > UTC, with cron fields read as
local wall-clock (no UTC pre-conversion)."""

from __future__ import annotations

import os
import time
from datetime import UTC, timedelta

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
        # Next fire computed in the deployment-default timezone: local wall-clock 18:00.
        assert str(job.next_run_time.tzinfo) == "Asia/Shanghai"
        assert job.next_run_time.hour == 18
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
        assert str(job.next_run_time.tzinfo) == "Asia/Shanghai"
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
        assert str(job.next_run_time.tzinfo) == "America/New_York"
        assert job.next_run_time.hour == 9
    finally:
        await scheduler.shutdown()


# ── once run_at: naive input is local wall-clock in the task timezone (F3) ──────


async def test_tool_create_once_naive_run_at_uses_task_timezone(isolated_schedule_db):
    """A naive once run_at is interpreted in the task's timezone, never the host
    process's system timezone (fix-cron-store-and-once F3 — AAA-8288/8279 class).

    Host TZ is forced to UTC for the duration of this test to make the pre-fix
    failure (implicit host-timezone interpretation) deterministic on any machine,
    then restored regardless of outcome.
    """
    original_tz = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        scheduler = cs.CronScheduler(settings=SchedulingSettings(default_timezone="UTC"))
        await scheduler.start()
        try:
            await builtin_tools.schedule(
                action="create",
                name="reminder",
                schedule_kind="once",
                run_at="2026-07-08 09:00",
                message="x",
                timezone="Asia/Shanghai",
            )
            task_id = _only_task_id()
            row = store.get(task_id)
            assert "+08:00" in row["run_at"], row["run_at"]

            job = scheduler.get_job(task_id)
            assert job is not None
            assert job.next_run_time.utcoffset() == timedelta(hours=8)
            # 09:00 Asia/Shanghai == 01:00 UTC — not 09:00 UTC (the pre-fix bug).
            assert job.next_run_time.astimezone(UTC).hour == 1
        finally:
            await scheduler.shutdown()
    finally:
        if original_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original_tz
        if hasattr(time, "tzset"):
            time.tzset()
