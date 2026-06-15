"""schedule create returns the next fire time (task timezone + UTC) and backfills
next_run_at, so a wrong timezone conversion is visible at creation time."""

from __future__ import annotations

import fleetent.cron_scheduler as cs
import fleetent.schedule_store as store
from fleetent.config import SchedulingSettings
from fleetent.tools import builtin_tools


async def test_create_echoes_next_fire_in_task_tz_and_utc(isolated_schedule_db):
    scheduler = cs.CronScheduler(settings=SchedulingSettings(default_timezone="UTC"))
    await scheduler.start()
    try:
        result = await builtin_tools.schedule(
            action="create",
            name="kb-pull",
            schedule_kind="cron",
            cron_expr="0 18 * * *",
            message="拉取知识库文档列表",
            timezone="Asia/Shanghai",
        )
        # The result states the next fire time in both the task timezone and UTC.
        assert "下次触发" in result
        assert "Asia/Shanghai" in result
        assert "UTC" in result

        # next_run_at is backfilled on the stored row.
        tasks = store.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["next_run_at"]  # non-empty
    finally:
        await scheduler.shutdown()


async def test_create_without_scheduler_does_not_echo_next_fire(isolated_schedule_db, monkeypatch):
    """No running scheduler → honest 'takes effect when running' message, no fabricated time."""
    monkeypatch.setattr(cs, "current", lambda: None)
    result = await builtin_tools.schedule(
        action="create",
        name="kb-pull",
        schedule_kind="cron",
        cron_expr="0 18 * * *",
        message="x",
        timezone="Asia/Shanghai",
    )
    assert "saved" in result
    assert "下次触发" not in result
    # persisted but with no next_run_at fabricated
    tasks = store.list_tasks()
    assert len(tasks) == 1
    assert not tasks[0]["next_run_at"]
