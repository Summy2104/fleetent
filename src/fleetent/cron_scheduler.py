"""APScheduler-backed cron scheduler for periodic agent runs."""

from __future__ import annotations

import logging
from contextlib import suppress
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]

import fleetent.schedule_store as _store
from fleetent.config import SchedulingSettings
from fleetent.user_store import DB_PATH as DB_PATH  # noqa: F401 — re-export for monkeypatching

logger = logging.getLogger(__name__)

LEGACY_CRON_CONFIG_PATH = Path("config/cron.yaml")


async def _agent_run(
    messages: list[dict[str, Any]], user_id: str, agent_name: str | None = None
) -> str:
    from fleetent import agent_loop

    return await agent_loop.run(messages, user_id=user_id, agent_name=agent_name)


async def _fire(task: dict[str, Any]) -> None:
    """Construct messages and dispatch agent run for a cron task."""
    messages = [{"role": "user", "content": task["message"]}]
    await _agent_run(messages, user_id=task["user_id"], agent_name=task.get("agent_name"))


class CronScheduler:
    def __init__(self, settings: SchedulingSettings | None = None) -> None:
        self._settings = settings or SchedulingSettings()
        self._scheduler = AsyncIOScheduler()

    @property
    def running(self) -> bool:
        return bool(self._scheduler.running)

    def get_job(self, job_id: str) -> Any:
        return self._scheduler.get_job(job_id)

    async def start(self) -> None:
        """Load persisted tasks from SQLite and start the scheduler."""

        if LEGACY_CRON_CONFIG_PATH.exists():
            raise RuntimeError(
                "Legacy config/cron.yaml is no longer supported; create cron jobs through "
                "SQLite-backed runtime management."
            )

        if not self._settings.enabled:
            return

        db_jobs = _store.list_tasks()

        for task in db_jobs:
            self._register(task)

        self._scheduler.start()

    def add_job(self, task: dict[str, Any]) -> None:
        self._register(task)

    def remove_job(self, task_id: str) -> None:
        with suppress(Exception):
            self._scheduler.remove_job(task_id)

    async def shutdown(self) -> None:
        import asyncio

        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            await asyncio.sleep(0)

    def _register(self, task: dict[str, Any]) -> None:

        async def _task_fire(t: dict[str, Any] = task) -> None:
            await _fire(t)

        fields = _parse_cron(task["cron_expr"])
        self._scheduler.add_job(
            _task_fire,
            trigger="cron",
            id=task["id"],
            timezone=task.get("timezone") or self._settings.default_timezone,
            replace_existing=True,
            **fields,
        )


def _parse_cron(expr: str) -> dict[str, str]:
    """Convert a 5-field cron expression to APScheduler keyword args."""
    minute, hour, day, month, day_of_week = expr.split()
    return {
        "minute": minute,
        "hour": hour,
        "day": day,
        "month": month,
        "day_of_week": day_of_week,
    }
