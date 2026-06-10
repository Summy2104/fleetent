"""APScheduler-backed cron scheduler for periodic agent runs."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]

import fleetent.schedule_store as _store
import fleetent.user_store as user_store
from fleetent import outbound
from fleetent.config import SchedulingSettings
from fleetent.identity import SYSTEM_PRINCIPAL, Principal
from fleetent.user_store import DB_PATH as DB_PATH  # noqa: F401 — re-export for monkeypatching

logger = logging.getLogger(__name__)

# A fired task whose final reply is exactly this sentinel runs successfully but
# delivers nothing — for "alert only when something changed" tasks.
_SILENT_SENTINEL = "[SILENT]"

# Missed runs after process downtime coalesce into a single fire within this window
# (APScheduler misfire_grace_time + coalesce); a one-shot past it is skipped, not fired
# late. max_instances=1 prevents a slow fire from overlapping its next trigger.
_MISFIRE_GRACE_SECONDS = 3600
_MAX_INSTANCES = 1

_RELATIVE_RUN_AT = re.compile(r"\+?(\d+)([smhd])")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _parse_run_at(run_at: str) -> datetime:
    """Resolve a one-shot ``run_at`` to a datetime: ISO-8601 absolute, or relative
    duration like ``+30m`` / ``2h`` (offset from now)."""
    spec = run_at.strip()
    match = _RELATIVE_RUN_AT.fullmatch(spec)
    if match:
        seconds = int(match.group(1)) * _UNIT_SECONDS[match.group(2)]
        return datetime.now(UTC) + timedelta(seconds=seconds)
    return datetime.fromisoformat(spec)


def _resolve_cron_principal(user_id: str) -> Principal | None:
    """Recheck user status before firing. Returns None if blocked or deleted."""
    if user_id == "system":
        return SYSTEM_PRINCIPAL
    u = user_store.get_by_id(user_id)
    if u is None or u.status == "blocked":
        return None
    return Principal(user_id=u.id, tenant_id=u.tenant_id)


async def _agent_run(
    messages: list[dict[str, Any]],
    user_id: str = "default",
    agent_name: str | None = None,
    principal: Principal | None = None,
) -> str:
    from fleetent.runtime import loop as agent_loop

    return await agent_loop.run(
        messages, user_id=user_id, agent_name=agent_name, principal=principal
    )


async def _fire(task: dict[str, Any], connectors: dict[str, Any] | None = None) -> None:
    """Construct messages, run the agent, and proactively deliver the reply (S3 + delivery).

    session_id binding:
    - None  → each fire derives a fresh, unique session `cron/{id}/{uuid}` and runs
      independently (no carried-over context).
    - set   → the task accumulates context in that fixed session.

    Delivery: the agent's final reply is sent at fire time to the resolved target
    (explicit ``deliver`` or, by default, the creation ``origin``) via the agent's live
    connector for that platform. ``[SILENT]`` suppresses delivery. Best-effort: a
    delivery failure is recorded on the task, never raised.
    """
    import uuid

    from fleetent.session import manager as session_mgr

    # Recheck user status before firing; skip if blocked or deleted.
    principal = _resolve_cron_principal(task["user_id"])
    if principal is None:
        logger.warning(
            "cron_fire_skipped task=%s reason=user_blocked_or_missing user_id=%s",
            task.get("id"),
            task.get("user_id"),
        )
        return

    sid_spec = task.get("session_id")
    if sid_spec is None:
        sid = f"cron/{task['id']}/{uuid.uuid4().hex}"
        messages: list[dict[str, Any]] = [{"role": "user", "content": task["message"]}]
    else:
        sid = sid_spec
        messages = list(await session_mgr.load(sid))
        messages.append({"role": "user", "content": task["message"]})

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        reply = await _agent_run(
            messages, agent_name=task.get("agent_name"), principal=principal
        )
    except Exception as exc:  # noqa: BLE001 — record the failure, never crash the scheduler
        logger.warning("cron_fire_run_failed task=%s error=%s", task.get("id"), exc)
        _record_run(task, now, "error", str(exc))
        return

    # agent_loop.run mutates `messages` in place into the full conversation; persist it
    # so a fixed-session task continues from here next fire.
    await session_mgr.save(
        sid, messages, user_id=principal.user_id, agent_name=task.get("agent_name")
    )

    delivery_error = await _deliver(task, reply, connectors or {})
    _record_run(task, now, "error" if delivery_error else "ok", delivery_error)


async def _deliver(
    task: dict[str, Any], reply: str | None, connectors: dict[str, Any]
) -> str | None:
    """Send the fired reply to the resolved target. Returns an error string or None.

    Target resolution: explicit ``deliver`` (mode=explicit) wins; otherwise fall back to
    the creation ``origin``. ``deliver.mode == "none"`` or a ``[SILENT]`` reply skips
    delivery. Unknown/absent connectors are logged and skipped (not an error per se).
    """
    if reply is None or reply.strip() == _SILENT_SENTINEL:
        return None
    target = _resolve_delivery(task)
    if target is None:
        return None
    platform, to, target_type, thread = target
    connector = connectors.get(platform)
    if connector is None:
        logger.warning("cron_deliver_no_connector task=%s platform=%s", task.get("id"), platform)
        return f"no connector for platform {platform}"
    try:
        sent = await outbound.send_to(
            platform, connector, to, reply, target_type=target_type, thread=thread
        )
    except Exception as exc:  # noqa: BLE001 — best-effort delivery
        logger.warning("cron_deliver_failed task=%s error=%s", task.get("id"), exc)
        return str(exc)
    return None if sent else "delivery returned false"


def _resolve_delivery(task: dict[str, Any]) -> tuple[str, str, str, Any] | None:
    """Resolve (platform, target, target_type, thread) at fire time, or None to skip."""
    deliver = task.get("deliver")
    if isinstance(deliver, dict):
        mode = deliver.get("mode", "origin")
        if mode == "none":
            return None
        if mode == "explicit":
            platform = deliver.get("platform")
            to = deliver.get("target")
            if platform and to:
                return (platform, to, deliver.get("target_type", "user"), deliver.get("thread"))
    origin = task.get("origin")
    if isinstance(origin, dict):
        platform = origin.get("platform")
        to = origin.get("chat_id")
        if platform and to:
            return (platform, to, origin.get("target_type", "user"), origin.get("thread_id"))
    return None


def _record_run(task: dict[str, Any], when: str, status: str, error: str | None) -> None:
    """Best-effort writeback of run-state columns; never raise from the fire path."""
    try:
        _store.update_run_state(task["id"], last_run_at=when, last_status=status, last_error=error)
    except Exception as exc:  # noqa: BLE001 — observability writeback is a side channel
        logger.warning("cron_run_state_writeback_failed task=%s error=%s", task.get("id"), exc)


class CronScheduler:
    def __init__(
        self,
        settings: SchedulingSettings | None = None,
        connectors_resolver: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._settings = settings or SchedulingSettings()
        self._scheduler = AsyncIOScheduler()
        # Resolved at fire time so a connector that connects after a job is registered
        # (or reconnects) is still reachable; None → no proactive delivery.
        self._connectors_resolver = connectors_resolver

    @property
    def running(self) -> bool:
        return bool(self._scheduler.running)

    def get_job(self, job_id: str) -> Any:
        return self._scheduler.get_job(job_id)

    async def start(self) -> None:
        """Load persisted tasks from SQLite and start the scheduler."""

        if not self._settings.enabled:
            return

        db_jobs = _store.list_tasks()

        for task in db_jobs:
            self._register(task)

        self._register_maintenance_jobs()
        self._scheduler.start()

    def _register_maintenance_jobs(self) -> None:
        from fleetent.tools.result_truncation import cleanup_spillover

        self._scheduler.add_job(
            cleanup_spillover,
            trigger="cron",
            hour=3,
            minute=0,
            id="__maintenance_spillover_cleanup__",
            replace_existing=True,
        )

    def add_job(self, task: dict[str, Any]) -> None:
        self._register(task)

    def add_interval_job(self, func: Any, seconds: int, job_id: str) -> None:
        """Register a fixed-interval background job (e.g. monitoring collection)."""
        self._scheduler.add_job(
            func,
            trigger="interval",
            seconds=seconds,
            id=job_id,
            replace_existing=True,
        )

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
            connectors = self._connectors_resolver() if self._connectors_resolver else None
            await _fire(t, connectors=connectors)

        tz = task.get("timezone") or self._settings.default_timezone
        common: dict[str, Any] = {
            "id": task["id"],
            "timezone": tz,
            "replace_existing": True,
            "misfire_grace_time": _MISFIRE_GRACE_SECONDS,
            "coalesce": True,
            "max_instances": _MAX_INSTANCES,
        }
        kind = task.get("schedule_kind") or "cron"
        if kind == "once":
            self._scheduler.add_job(
                _task_fire, trigger="date", run_date=_parse_run_at(task["run_at"]), **common
            )
        elif kind == "interval":
            self._scheduler.add_job(
                _task_fire, trigger="interval", seconds=int(task["interval_seconds"]), **common
            )
        else:
            self._scheduler.add_job(
                _task_fire, trigger="cron", **_parse_cron(task["cron_expr"]), **common
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
