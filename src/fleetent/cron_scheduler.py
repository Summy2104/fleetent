"""APScheduler-backed cron scheduler for periodic agent runs."""

from __future__ import annotations

import logging
from contextlib import suppress
from pathlib import Path
from typing import Any

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]

import fleetent.schedule_store as _store
from fleetent.user_store import DB_PATH as DB_PATH  # noqa: F401 — re-export for monkeypatching

logger = logging.getLogger(__name__)

_CRON_YAML_PATH = Path("config/cron.yaml")


async def _agent_run(
    messages: list[dict[str, Any]], user_id: str, agent_name: str | None = None
) -> str:
    from fleetent import agent_loop

    return await agent_loop.run(messages, user_id=user_id, agent_name=agent_name)


async def _fire(task: dict[str, Any]) -> None:
    """Construct messages and dispatch agent run for a cron task."""
    messages = [{"role": "user", "content": task["message"]}]
    await _agent_run(messages, user_id=task["user_id"], agent_name=task.get("agent_name"))


def load_cron_yaml(path: Path) -> list[dict[str, Any]]:
    """Load static job definitions from a YAML file. Returns [] if missing."""
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text()) or {}
    jobs = []
    for entry in raw.get("jobs", []):
        try:
            jobs.append(
                {
                    "id": entry["id"],
                    "name": entry["name"],
                    "cron_expr": entry["cron"],
                    "timezone": entry.get("timezone", "UTC"),
                    "user_id": entry["user_id"],
                    "agent_name": entry.get("agent_name"),
                    "message": entry["message"],
                    "enabled": 1,
                    "source": "static",
                }
            )
        except KeyError as exc:
            logger.warning("cron_yaml_skip_entry id=%s missing_field=%s", entry.get("id"), exc)
    return jobs


class CronScheduler:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()

    @property
    def running(self) -> bool:
        return bool(self._scheduler.running)

    def get_job(self, job_id: str) -> Any:
        return self._scheduler.get_job(job_id)

    async def start(self) -> None:
        """Load all tasks from YAML + SQLite and start the scheduler."""

        yaml_jobs = load_cron_yaml(_CRON_YAML_PATH)
        db_jobs = _store.list_tasks()

        # Merge: SQLite takes priority over YAML for same id
        db_ids = {j["id"] for j in db_jobs}
        merged = db_jobs + [j for j in yaml_jobs if j["id"] not in db_ids]

        for task in merged:
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
            timezone=task.get("timezone", "UTC"),
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
