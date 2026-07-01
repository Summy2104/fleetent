"""First-start backfill of next_run_at for tasks persisted without one."""

from __future__ import annotations

from datetime import UTC, datetime

import fleetent.cron_scheduler as cs
import fleetent.schedule_store as store
from fleetent.config import SchedulingSettings


async def test_start_backfills_missing_next_run_at(isolated_schedule_db):
    # A task persisted before the poll engine (or freshly created) has no next_run_at.
    task = store.create(
        name="legacy",
        cron_expr="0 9 * * *",
        timezone="UTC",
        user_id="u-1",
        message="hi",
        source="dynamic",
        schedule_kind="cron",
    )
    assert store.get(task["id"])["next_run_at"] is None

    scheduler = cs.CronScheduler(settings=SchedulingSettings())
    await scheduler.start()
    try:
        row = store.get(task["id"])
        assert row["next_run_at"] is not None  # backfilled on start
        assert datetime.fromisoformat(row["next_run_at"]) > datetime.now(UTC)
    finally:
        await scheduler.shutdown()
