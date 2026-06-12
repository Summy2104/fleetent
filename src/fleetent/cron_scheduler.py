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


def _resolve_cron_principal(task: dict[str, Any]) -> Principal | None:
    """Recheck the archived identity in its own domain before firing.

    Platform users (present in the users table) keep platform semantics: blocked →
    reject; a row that disappeared (deleted user) with no IM origin → reject.
    Channel-guaranteed IM identities never live in the users table (the identity-port
    spec forbids resolving them through user_store), so a task carrying an IM origin
    fires with its archived identity. Deployments without user management (no users
    table at all) trust the archived identity — the agent-independence baseline.
    """
    user_id = str(task.get("user_id") or "default")
    if user_id == "system":
        return SYSTEM_PRINCIPAL
    if user_id == "default":  # placeholder, no platform identity claimed
        return Principal(user_id="default", tenant_id="default")
    try:
        u = user_store.get_by_id(user_id)
    except Exception:  # noqa: BLE001 — users table absent: no platform domain to consult
        return Principal(user_id=user_id, tenant_id="default")
    if u is not None:
        if u.status == "blocked":
            return None
        return Principal(user_id=u.id, tenant_id=u.tenant_id)
    origin = task.get("origin")
    if isinstance(origin, dict) and origin.get("platform"):
        # Channel-guaranteed IM identity: the edge authenticated the creator.
        return Principal(user_id=user_id, tenant_id="default")
    return None


async def _agent_run(
    messages: list[dict[str, Any]],
    user_id: str = "default",
    agent_name: str | None = None,
    principal: Principal | None = None,
    connectors: dict[str, Any] | None = None,
) -> str:
    from fleetent.runtime import loop as agent_loop

    # Thread the fire-time connector snapshot so outbound IM tools invoked inside the
    # fired run (send_im_message, ...) reach the live connector — a cron fire has no
    # inbound-message context to carry them otherwise (AAA-8039).
    return await agent_loop.run(
        messages,
        agent_name=agent_name,
        principal=principal,
        outbound_connectors=connectors or {},
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

    # Recheck the archived identity in its own domain; skip when its domain rejects it.
    principal = _resolve_cron_principal(task)
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
            messages,
            agent_name=task.get("agent_name"),
            principal=principal,
            connectors=connectors,
        )
    except Exception as exc:  # noqa: BLE001 — record the failure, never crash the scheduler
        logger.warning("cron_fire_run_failed task=%s error=%s", task.get("id"), exc)
        _record_run(task, now, "error", str(exc))
        return

    # agent_loop.run mutates `messages` in place into the full conversation; persist it
    # so a fixed-session task continues from here next fire.
    await session_mgr.save(sid, messages, user_id=principal.user_id)

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


# Process-wide handle to the running scheduler (one agent per process). Set by
# start(), cleared by shutdown(); the tool layer mutates tasks through it so the
# store write and the live job registration cannot drift apart (single owner).
_current: CronScheduler | None = None


def current() -> CronScheduler | None:
    """Return the running scheduler instance, or None outside the service lifecycle."""
    return _current


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
        global _current
        _current = self

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

        global _current
        if _current is self:
            _current = None
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            await asyncio.sleep(0)

    # ── Single mutation owner: store write + live job registration in one place ──

    def create_task(
        self,
        *,
        name: str,
        schedule_kind: str = "cron",
        cron_expr: str | None = None,
        run_at: str | None = None,
        interval_seconds: int | None = None,
        timezone: str = "UTC",
        user_id: str = "default",
        message: str = "",
        source: str = "tool",
        session_id: str | None = None,
        origin: dict[str, Any] | None = None,
        deliver: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist a new task and register its live job in one step."""
        task = _store.create(
            name=name,
            cron_expr=cron_expr,
            timezone=timezone,
            user_id=user_id,
            message=message,
            source=source,
            session_id=session_id,
            schedule_kind=schedule_kind,
            run_at=run_at,
            interval_seconds=interval_seconds,
            origin=origin,
            deliver=deliver,
        )
        self._register(task)
        return task

    def remove_task(self, task_id: str) -> bool:
        """Delete the task row and deregister its live job. Returns False if unknown."""
        deleted = _store.delete(task_id)
        self.remove_job(task_id)
        return deleted

    def set_task_enabled(self, task_id: str, enabled: bool) -> bool:
        """Toggle the enabled flag and (de)register the live job accordingly."""
        matched = _store.set_enabled(task_id, enabled)
        if not matched:
            return False
        if enabled:
            task = _store.get(task_id)
            if task is not None:
                self._register(task)
        else:
            self.remove_job(task_id)
        return True

    def _complete_once(self, task_id: str) -> None:
        """Mark a fired one-shot done so it never looks alive in the store again.

        Only a successful run (last_status == "ok") flips to "completed"; a failed run
        keeps its error state and stays enabled so boot-time misfire policy governs it.
        """
        row = _store.get(task_id)
        if row is None or row.get("last_status") != "ok":
            return
        _store.set_enabled(task_id, False)
        with suppress(Exception):
            _store.update_run_state(
                task_id,
                last_run_at=row.get("last_run_at"),
                last_status="completed",
                last_error=None,
            )

    async def run_now(self, task_id: str) -> bool:
        """Fire the task immediately without altering its schedule. False if unknown."""
        task = _store.get(task_id)
        if task is None:
            return False
        connectors = self._connectors_resolver() if self._connectors_resolver else None
        await _fire(task, connectors=connectors)
        return True

    def _register(self, task: dict[str, Any]) -> None:

        async def _task_fire(task_id: str = task["id"]) -> None:
            # Revalidate against the store at fire time: a row deleted or disabled by
            # a writer that bypassed the facade must never execute. The fresh row (not
            # the dict captured at registration) is the execution payload.
            row = _store.get(task_id)
            if row is None or not row.get("enabled"):
                logger.warning("cron_fire_skipped task=%s reason=missing_or_disabled", task_id)
                self.remove_job(task_id)
                return
            connectors = self._connectors_resolver() if self._connectors_resolver else None
            await _fire(row, connectors=connectors)
            if (row.get("schedule_kind") or "cron") == "once":
                self._complete_once(task_id)

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


# ── Module-level facade: the mutation API for callers without an instance handle ──
# (the tool layer). Routes through the running scheduler when present so the live
# job registration cannot drift from the store; degrades to store-only otherwise
# (picked up at next boot).


def create_task(
    *,
    name: str,
    schedule_kind: str = "cron",
    cron_expr: str | None = None,
    run_at: str | None = None,
    interval_seconds: int | None = None,
    timezone: str = "UTC",
    user_id: str = "default",
    message: str = "",
    source: str = "tool",
    session_id: str | None = None,
    origin: dict[str, Any] | None = None,
    deliver: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a task; registers the live job when a scheduler is running."""
    kwargs: dict[str, Any] = {
        "name": name,
        "schedule_kind": schedule_kind,
        "cron_expr": cron_expr,
        "run_at": run_at,
        "interval_seconds": interval_seconds,
        "timezone": timezone,
        "user_id": user_id,
        "message": message,
        "source": source,
        "session_id": session_id,
        "origin": origin,
        "deliver": deliver,
    }
    sched = current()
    if sched is not None:
        return sched.create_task(**kwargs)
    return _store.create(**kwargs)


def remove_task(task_id: str) -> bool:
    """Delete a task; deregisters the live job when a scheduler is running."""
    sched = current()
    if sched is not None:
        return sched.remove_task(task_id)
    return _store.delete(task_id)


def set_task_enabled(task_id: str, enabled: bool) -> bool:
    """Toggle a task; (de)registers the live job when a scheduler is running."""
    sched = current()
    if sched is not None:
        return sched.set_task_enabled(task_id, enabled)
    return _store.set_enabled(task_id, enabled)


def list_tasks(include_disabled: bool = False) -> list[dict[str, Any]]:
    """Read-only passthrough for the tool layer."""
    return _store.list_tasks(include_disabled=include_disabled)


async def run_task_now(task_id: str) -> bool:
    """Fire a task immediately. Returns False if the task does not exist."""
    sched = current()
    if sched is not None:
        return await sched.run_now(task_id)
    task = _store.get(task_id)
    if task is None:
        return False
    await _fire(task)
    return True


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
