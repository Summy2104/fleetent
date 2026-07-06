"""Durable next_run_at poll scheduler for periodic agent runs.

The engine drives firing from a persisted per-task ``next_run_at`` plus a lightweight
in-process asyncio tick loop, not from an in-memory trigger registry. On each tick it
selects due tasks (``next_run_at <= now``), advances a recurring task's ``next_run_at``
BEFORE executing it (decoupling cadence from run duration; at-most-once), and dispatches
the run under a bounded-concurrency semaphore. APScheduler's ``CronTrigger`` is reused only
as pure cron math (see ``compute_next_run``); the scheduling engine itself is the poll loop.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any, cast

import fleetent.schedule_store as _store
from fleetent import outbound
from fleetent.config import SchedulingSettings
from fleetent.identity import SYSTEM_PRINCIPAL, Principal

logger = logging.getLogger(__name__)

# Poll-engine defaults (overridable via SchedulingSettings).
_DEFAULT_TICK_INTERVAL_SECONDS = 10.0
_DEFAULT_MAX_PARALLEL = 4
_DEFAULT_HISTORY_RETENTION = 50
_MAINTENANCE_SPILLOVER_ID = "__maintenance_spillover_cleanup__"

# A fired task whose final reply is this sentinel runs successfully but delivers
# nothing — for "alert only when something changed" tasks.
_SILENT_SENTINEL = "[SILENT]"


def _is_silent_reply(reply: str | None) -> bool:
    """Whether a fired task's reply is the silent-skip sentinel.

    Robust to trailing content (whitespace, or an accidentally appended delivery trailer):
    a reply is silent when it is None/blank, or its first non-blank line equals the
    sentinel. This prevents leaking ``[SILENT]`` (or anything appended after it) to the
    user when something tacks text onto the model's bare sentinel reply.
    """
    if reply is None:
        return True
    stripped = reply.strip()
    if not stripped:
        return True
    return stripped.splitlines()[0].strip() == _SILENT_SENTINEL


_RELATIVE_RUN_AT = re.compile(r"\+?(\d+)([smhd])")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _parse_run_at(run_at: str, tz: str | None = None) -> datetime:
    """Resolve a one-shot ``run_at`` to a datetime: ISO-8601 absolute, or relative
    duration like ``+30m`` / ``2h`` (offset from now).

    A genuinely naive input (no explicit offset, and no ``Z``/``UTC``/``GMT`` suffix)
    is interpreted as **local wall-clock time in ``tz``** (fix-cron-store-and-once F3)
    — never the host process's system timezone, which the tool's own contract
    explicitly disclaims ("run_at 按 timezone 的本地时间解释"). ``tz=None`` resolves to
    UTC (``_as_tzinfo``'s fallback), preserving prior behavior for UTC-deployed hosts.
    An input that already carries an explicit offset/Z/UTC/GMT suffix is unaffected —
    ``tz`` never re-interprets an already-aware value.
    """
    spec = run_at.strip()
    match = _RELATIVE_RUN_AT.fullmatch(spec)
    if match:
        seconds = int(match.group(1)) * _UNIT_SECONDS[match.group(2)]
        return datetime.now(UTC) + timedelta(seconds=seconds)
    # Tolerate common non-strict ISO forms the model emits (cron-runat-hardening): a trailing
    # ` UTC`/` GMT` name → numeric offset; a trailing `Z` → `+00:00` (defensive on older
    # interpreters). fromisoformat already accepts the space-separated `YYYY-MM-DD HH:MM:SS`.
    spec = re.sub(r"\s+(?:UTC|GMT)\s*$", "+00:00", spec, flags=re.IGNORECASE)
    if spec.endswith(("Z", "z")):
        spec = spec[:-1] + "+00:00"
    dt = datetime.fromisoformat(spec)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_as_tzinfo(tz))
    return dt


def _as_tzinfo(tz: str | None) -> tzinfo:
    """Resolve a timezone name to a tzinfo (UTC fallback), for cron next-fire math."""
    from zoneinfo import ZoneInfo

    if not tz:
        return UTC
    try:
        return ZoneInfo(tz)
    except Exception:  # noqa: BLE001 — unknown tz name → safe UTC fallback
        return UTC


def compute_next_run(
    kind: str,
    *,
    cron_expr: str | None = None,
    interval_seconds: int | None = None,
    run_at: Any = None,
    base: datetime | None = None,
    now: datetime | None = None,
    tz: str = "UTC",
) -> datetime | None:
    """Compute a task's next fire time (engine-internal, no in-memory trigger registry).

    - ``once``: returns the fixed ``run_at`` (parsed if a string); no advancement.
    - ``interval``: ``base + interval``; if that is already at/behind ``now`` (a stale/slow
      schedule) it is fast-forwarded in whole periods to the first FUTURE occurrence — at
      most once for the missed window, never a burst. ``base=None`` → ``now + interval``.
    - ``cron``: the next fire strictly after ``now`` (APScheduler ``CronTrigger`` is reused
      purely for the cron math; the scheduler engine itself is the poll loop).
    """
    if now is None:
        now = datetime.now(UTC)
    if kind == "once":
        if isinstance(run_at, str):
            return _parse_run_at(run_at, tz=tz)
        return cast("datetime | None", run_at)
    if kind == "interval":
        if not interval_seconds or int(interval_seconds) <= 0:
            raise ValueError("interval task requires a positive interval_seconds")
        step = timedelta(seconds=int(interval_seconds))
        if base is None:
            return now + step
        nxt = base + step
        if nxt <= now:
            missed = (now - base) // step
            nxt = base + step * (missed + 1)
        return nxt
    if kind == "cron":
        if not cron_expr:
            raise ValueError("cron task requires cron_expr")
        from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]

        trigger = CronTrigger.from_crontab(cron_expr, timezone=_as_tzinfo(tz))
        # get_next_fire_time floors on `previous`, not `now`; seed with max(base, now) so a
        # stale base (process was down) fast-forwards to the first fire at/after now.
        prev = now if base is None else max(base, now)
        return cast("datetime | None", trigger.get_next_fire_time(prev, now))
    raise ValueError(f"invalid schedule kind: {kind!r} (cron/once/interval)")


# Fire-time creator recheck, injection-decoupled from the platform management DB
# (decouple-cron-principal-recheck). The platform installs a resolver at startup
# (server.py lifespan, mirroring user_store.set_api_key_resolver); standalone never
# installs one and trusts the task's archived IM identity. cron_scheduler therefore
# never imports user_store or opens the management database on the fire path.
_principal_resolver: Callable[[dict[str, Any]], Principal | None] | None = None


def set_principal_resolver(resolver: Callable[[dict[str, Any]], Principal | None]) -> None:
    """Install the platform fire-time creator recheck (blocked/deleted against `users`).

    Called by the platform control plane at startup. The standalone agent never calls
    this, so `_resolve_cron_principal` falls back to trusting the archived IM identity
    without touching any management database.
    """
    global _principal_resolver
    _principal_resolver = resolver


def _resolve_cron_principal(task: dict[str, Any]) -> Principal | None:
    """Resolve the principal a fired task runs as, decoupled from platform storage.

    `system`/`default` short-circuit (no resolver, no DB). Otherwise: when a platform
    resolver is installed it owns the recheck (blocked → reject; vanished without IM
    origin → reject; else current Principal). When none is installed (standalone agent),
    trust the task's archived IM identity — the edge authenticated the creator at
    creation time — and fail closed only when there is no IM provenance to trust.
    """
    user_id = str(task.get("user_id") or "default")
    if user_id == "system":
        return SYSTEM_PRINCIPAL
    if user_id == "default":  # placeholder, no platform identity claimed
        return Principal(user_id="default", tenant_id="default")
    if _principal_resolver is not None:
        # Platform mode: delegate the users-table revocation recheck. A lookup failure
        # (locked DB, I/O error) fails closed — never fire a task we cannot reverify.
        try:
            return _principal_resolver(task)
        except Exception as exc:  # noqa: BLE001 — unverifiable identity: fail closed
            logger.warning(
                "cron_principal_recheck_failed task=%s user_id=%s err=%s",
                task.get("id"),
                user_id,
                exc,
            )
            return None
    # Standalone: no user-management domain to reverify against. Trust the archived,
    # edge-authenticated IM identity (the agent-independence baseline); never open the
    # management database — so an empty/malformed DATABASE_URL cannot skip a fire.
    return Principal(user_id=user_id, tenant_id="default")


async def _agent_run(
    messages: list[dict[str, Any]],
    user_id: str = "default",
    agent_name: str | None = None,
    principal: Principal | None = None,
    connectors: dict[str, Any] | None = None,
    suppress_outbound: bool = False,
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
        # A fired task has no interlocutor; its reply is broadcast verbatim. The operator-
        # facing delivery trailer would pollute the broadcast and corrupt the [SILENT]
        # skip sentinel, so it is suppressed for fired runs.
        emit_delivery_trailer=False,
        # generate-fires-exclude-outbound-tools: a `generate` fire's reply is delivered by the
        # scheduler, so its run must not expose outbound tools (else the model self-delivers and
        # duplicates the broadcast). `action` fires keep them (they deliver via their own tools).
        suppress_outbound_tools=suppress_outbound,
    )


def _generate_delivery_statement(task: dict[str, Any]) -> str:
    """The fired-run delivery contract for a ``generate`` task (no interlocutor at fire time).

    Names the delivery target, restricts the reply to the notification body, documents the
    ``[SILENT]`` skip sentinel, and forbids questions/operator-facing commentary — so the
    agent's final reply is a clean notification that the scheduler broadcasts verbatim.
    """
    target = _resolve_delivery(task)
    where = f"{target[0]}:{target[1]}" if target else "the task's configured target"
    return (
        f"[定时任务] 这是一个到点自动触发的任务，你没有对话对象，不要提问、不要输出面向操作者的"
        f"说明。你这条回复的最终内容将被原样发布到 {where}。回复中只应包含要发布的通知正文本身；"
        f"若本次无需发布任何内容，只回复 {_SILENT_SENTINEL}。"
    )


async def _maybe_alert_failure(
    task: dict[str, Any], error_text: str, connectors: dict[str, Any] | None
) -> None:
    """Best-effort failure alert to the task's resolvable delivery target.

    Reuses the frozen-text ``_deliver`` path (no agent run) — same target resolution,
    same live-connector send, same delivery trace. When the target cannot be resolved
    (or is explicitly ``deliver.mode="none"``), ``_deliver`` degrades to a no-op and no
    alert is attempted — there is nowhere to send it.

    Suppressed when the task's `last_status` — as read from the row at the START of
    this fire, i.e. the PREVIOUS fire's outcome — was already ``"error"``: a recurring
    task in a failure streak alerts only once, not on every tick. A `once` task (whose
    `last_status` is `None` the one time it can fail) always alerts.
    """
    if task.get("last_status") == "error":
        return
    name = task.get("name") or task.get("id")
    alert_text = f"⚠️ 定时任务 {name} 执行失败: {error_text}"
    try:
        await _deliver(task, alert_text, connectors or {})
    except Exception as exc:  # noqa: BLE001 — alerting is best-effort, never break a fire
        logger.warning("cron_fire_alert_failed task=%s error=%s", task.get("id"), exc)


async def _fire(
    task: dict[str, Any],
    connectors: dict[str, Any] | None = None,
    history_retention: int = _DEFAULT_HISTORY_RETENTION,
) -> None:
    """Construct messages, run the agent, and proactively deliver the reply (S3 + delivery).

    session_id binding:
    - None  → each fire derives a fresh, unique session `cron/{id}/{uuid}` and runs
      independently (no carried-over context).
    - set   → the task accumulates context in that fixed session.

    Delivery: the agent's final reply is sent at fire time to the resolved target
    (explicit ``deliver`` or, by default, the creation ``origin``) via the agent's live
    connector for that platform. ``[SILENT]`` suppresses delivery. Best-effort: a
    delivery failure is recorded on the task, never raised. Every fire outcome (including a
    ``skipped`` occurrence whose principal cannot be verified) is appended to run history so
    the recurring behavior is auditable and never silently dropped.
    """
    import uuid

    from fleetent.session import manager as session_mgr

    started = datetime.now(UTC)
    now = started.strftime("%Y-%m-%dT%H:%M:%SZ")
    task_type = task.get("task_type") or "generate"

    def _elapsed_ms() -> int:
        return int((datetime.now(UTC) - started).total_seconds() * 1000)

    # Recheck the archived identity in its own domain; skip when its domain rejects it. The
    # skip is recorded (not silently dropped) so a due occurrence is always accounted for.
    principal = _resolve_cron_principal(task)
    if principal is None:
        logger.warning(
            "cron_fire_skipped task=%s reason=user_blocked_or_missing user_id=%s",
            task.get("id"),
            task.get("user_id"),
        )
        _record_history(
            task,
            now,
            "skipped",
            agent_error="principal unverified (blocked or missing)",
            kind=task_type,
            duration_ms=_elapsed_ms(),
            retention=history_retention,
        )
        return

    # notify: deterministic — the scheduler sends the frozen copy verbatim, no agent run.
    # Status reflects the delivery outcome (the task intent).
    if task_type == "notify":
        delivery_error = await _deliver(task, task.get("notify_text"), connectors or {})
        status = "error" if delivery_error else "ok"
        _record_run(task, now, status, delivery_error)
        _record_history(
            task,
            now,
            status,
            delivery_error=delivery_error,
            kind=task_type,
            duration_ms=_elapsed_ms(),
            retention=history_retention,
        )
        if status == "error":
            await _maybe_alert_failure(task, delivery_error or "delivery failed", connectors)
        return

    sid_spec = task.get("session_id")
    sid = f"cron/{task['id']}/{uuid.uuid4().hex}" if sid_spec is None else sid_spec
    messages: list[dict[str, Any]] = [] if sid_spec is None else list(await session_mgr.load(sid))
    # generate: the run's final reply IS the broadcast — fold the delivery contract into the
    # turn's instruction so the agent emits only the notification body (no questions;
    # [SILENT] to send nothing). One user message (no separate turn) keeps fixed-session
    # history clean.
    content = task["message"]
    if task_type == "generate":
        content = f"{_generate_delivery_statement(task)}\n\n{content}"
    messages.append({"role": "user", "content": content})

    try:
        reply = await _agent_run(
            messages,
            agent_name=task.get("agent_name"),
            principal=principal,
            connectors=connectors,
            # generate delivers via the scheduler → suppress outbound tools in the run;
            # action delivers via its own tools → keep them.
            suppress_outbound=(task_type == "generate"),
        )
    except Exception as exc:  # noqa: BLE001 — record the failure, never crash the scheduler
        logger.warning("cron_fire_run_failed task=%s error=%s", task.get("id"), exc)
        _record_run(task, now, "error", str(exc))
        _record_history(
            task,
            now,
            "error",
            agent_error=str(exc),
            kind=task_type,
            duration_ms=_elapsed_ms(),
            retention=history_retention,
        )
        await _maybe_alert_failure(task, str(exc), connectors)
        return

    # agent_loop.run mutates `messages` in place into the full conversation; persist it
    # so a fixed-session task continues from here next fire.
    await session_mgr.save(sid, messages, user_id=principal.user_id)

    # action: the agent delivers via its own tools during the run — the scheduler MUST NOT
    # broadcast its final reply (it is an operator-facing run report). Status = run outcome.
    if task_type == "action":
        _record_run(task, now, "ok", None)
        _record_history(
            task, now, "ok", kind=task_type, duration_ms=_elapsed_ms(), retention=history_retention
        )
        return

    delivery_error = await _deliver(task, reply, connectors or {})
    if (
        delivery_error is None
        and not _is_silent_reply(reply)
        and _resolve_delivery(task) is None
        and not _is_explicit_no_delivery(task)
    ):
        # A broadcast task's output has nowhere to go — origin missing and no explicit
        # deliver — is a failure, not a success (fix-cron-store-and-once F2c). The lone
        # exception is a deliberate deliver.mode="none" (checked above), which stays ok.
        delivery_error = "no_delivery_target"
    status = "error" if delivery_error else "ok"
    _record_run(task, now, status, delivery_error)
    _record_history(
        task,
        now,
        status,
        delivery_error=delivery_error,
        kind=task_type,
        duration_ms=_elapsed_ms(),
        retention=history_retention,
    )
    if status == "error":
        await _maybe_alert_failure(task, delivery_error or "delivery failed", connectors)


async def _deliver(
    task: dict[str, Any], reply: str | None, connectors: dict[str, Any]
) -> str | None:
    """Send the fired reply to the resolved target. Returns an error string or None.

    Target resolution: explicit ``deliver`` (mode=explicit) wins; otherwise fall back to
    the creation ``origin``. ``deliver.mode == "none"`` or a ``[SILENT]`` reply skips
    delivery. Unknown/absent connectors are logged and skipped (not an error per se).
    """
    if _is_silent_reply(reply):
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
        receipt = await outbound.send_to(
            platform, connector, to, reply, target_type=target_type, thread=thread
        )
    except Exception as exc:  # noqa: BLE001 — best-effort delivery
        logger.warning("cron_deliver_failed task=%s error=%s", task.get("id"), exc)
        return str(exc)
    # delivery-receipts (§2, D2): cron has no ToolContext, so it self-records the delivery
    # trace here (run_id keyed by the task so a cron fire's delivery is auditable).
    from fleetent.observability import traces

    traces.record_delivery(
        f"cron:{task.get('id')}",
        None,
        {
            "ok": receipt.ok,
            "platform": receipt.platform,
            "target": receipt.target,
            "target_type": receipt.target_type,
            "kind": receipt.kind,
            "provider_ref": receipt.provider_ref,
            "error": receipt.error,
        },
    )
    return None if receipt.ok else (receipt.error or "delivery returned false")


def _is_explicit_no_delivery(task: dict[str, Any]) -> bool:
    """Whether the task deliberately opts out of delivery (``deliver.mode="none"``).

    Distinguishes "intentionally silent" from "target unresolvable" — only the latter
    is a failure for a broadcast (`generate`) task (fix-cron-store-and-once F2c).
    """
    deliver = task.get("deliver")
    return isinstance(deliver, dict) and deliver.get("mode") == "none"


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
        addr = outbound.ConversationAddress.from_cron_origin(origin)
        if addr.platform and addr.chat_id:
            return (addr.platform, addr.chat_id, addr.target_type, addr.thread_id)
    return None


def _record_run(task: dict[str, Any], when: str, status: str, error: str | None) -> None:
    """Best-effort writeback of run-state columns; never raise from the fire path."""
    try:
        _store.update_run_state(task["id"], last_run_at=when, last_status=status, last_error=error)
    except Exception as exc:  # noqa: BLE001 — observability writeback is a side channel
        logger.warning("cron_run_state_writeback_failed task=%s error=%s", task.get("id"), exc)


def _record_history(
    task: dict[str, Any],
    when: str,
    status: str,
    *,
    agent_error: str | None = None,
    delivery_error: str | None = None,
    kind: str | None = None,
    duration_ms: int | None = None,
    retention: int = _DEFAULT_HISTORY_RETENTION,
) -> None:
    """Append one run-history row (agent vs delivery error separated); never raise.

    Best-effort exactly like ``_record_run``: a history-write failure is logged and does not
    change the fire outcome or crash the scheduler.
    """
    try:
        _store.record_run(
            task["id"],
            status=status,
            fired_at=when,
            kind=kind,
            agent_error=agent_error,
            delivery_error=delivery_error,
            duration_ms=duration_ms,
            retention=retention,
        )
    except Exception as exc:  # noqa: BLE001 — history is a side channel, never break a fire
        logger.warning("cron_run_history_writeback_failed task=%s error=%s", task.get("id"), exc)


# Process-wide handle to the running scheduler (one agent per process). Set by
# start(), cleared by shutdown(); the tool layer mutates tasks through it so the
# store write and the live job registration cannot drift apart (single owner).
_current: CronScheduler | None = None


def current() -> CronScheduler | None:
    """Return the running scheduler instance, or None outside the service lifecycle."""
    return _current


@dataclass
class _JobView:
    """A registered job's live view: its fire callable and cached next fire time.

    Kept so ``get_job(id)`` reflects registration/next-run without an in-memory trigger
    engine. ``func`` performs the fire (store-revalidated) for scheduled tasks, or the
    maintenance callable for internal periodic jobs.
    """

    func: Callable[[], Awaitable[None]] | Callable[[], Any]
    next_run_time: datetime | None = None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


class CronScheduler:
    def __init__(
        self,
        settings: SchedulingSettings | None = None,
        connectors_resolver: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._settings = settings or SchedulingSettings()
        # Resolved at fire time so a connector that connects after a job is registered
        # (or reconnects) is still reachable; None → no proactive delivery.
        self._connectors_resolver = connectors_resolver
        self._jobs: dict[str, _JobView] = {}
        self._running = False
        self._tick_task: asyncio.Task[None] | None = None
        self._inflight: set[str] = set()
        # Internal fixed-interval periodic jobs (maintenance, monitoring): job_id → period.
        self._periodic_intervals: dict[str, timedelta] = {}
        self._tick_interval = float(
            getattr(self._settings, "tick_interval_seconds", _DEFAULT_TICK_INTERVAL_SECONDS)
            or _DEFAULT_TICK_INTERVAL_SECONDS
        )
        self._max_parallel = int(
            getattr(self._settings, "max_parallel", _DEFAULT_MAX_PARALLEL) or _DEFAULT_MAX_PARALLEL
        )
        self._history_retention = int(
            getattr(self._settings, "history_retention", _DEFAULT_HISTORY_RETENTION)
            or _DEFAULT_HISTORY_RETENTION
        )
        self._sem = asyncio.Semaphore(self._max_parallel)

    @property
    def running(self) -> bool:
        return self._running

    def get_job(self, job_id: str) -> _JobView | None:
        return self._jobs.get(job_id)

    async def start(self) -> None:
        """Register persisted tasks (backfilling next_run_at) and start the tick loop."""
        if not self._settings.enabled:
            return
        for task in _store.list_tasks():
            # Bulkhead (cron-runat-hardening): one malformed task (e.g. an unparseable
            # run_at) must never crash agent boot. Log it, disable it so it is not re-loaded
            # next boot, and continue registering the rest.
            try:
                self._register(task)
            except Exception as exc:  # noqa: BLE001 — one bad row is a data problem, not an outage
                task_id = task.get("id")
                logger.warning("cron_register_failed task=%s error=%s", task_id, exc)
                if task_id:
                    with suppress(Exception):
                        _store.set_enabled(task_id, False)
        self._register_maintenance_jobs()
        self._running = True
        self._tick_task = asyncio.create_task(self._run_tick_loop())
        global _current
        _current = self

    def _register_maintenance_jobs(self) -> None:
        from fleetent.tools.result_truncation import cleanup_spillover

        now = datetime.now(UTC)
        nxt = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        self._jobs[_MAINTENANCE_SPILLOVER_ID] = _JobView(func=cleanup_spillover, next_run_time=nxt)
        self._periodic_intervals[_MAINTENANCE_SPILLOVER_ID] = timedelta(days=1)

    def add_job(self, task: dict[str, Any]) -> None:
        self._register(task)

    def add_interval_job(self, func: Callable[[], Any], seconds: int, job_id: str) -> None:
        """Register a fixed-interval internal periodic job (e.g. monitoring collection)."""
        self._jobs[job_id] = _JobView(
            func=func, next_run_time=datetime.now(UTC) + timedelta(seconds=seconds)
        )
        self._periodic_intervals[job_id] = timedelta(seconds=seconds)

    def remove_job(self, task_id: str) -> None:
        self._jobs.pop(task_id, None)
        self._periodic_intervals.pop(task_id, None)

    async def shutdown(self) -> None:
        global _current
        if _current is self:
            _current = None
        self._running = False
        if self._tick_task is not None:
            self._tick_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._tick_task
            self._tick_task = None

    # ── poll loop ────────────────────────────────────────────────────────────

    async def _run_tick_loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — a bad tick must not kill the loop
                logger.warning("cron_tick_failed error=%s", exc)
            try:
                await asyncio.sleep(self._tick_interval)
            except asyncio.CancelledError:
                raise

    async def _tick(self, now: datetime | None = None) -> list[asyncio.Task[None]]:
        """Run one poll iteration: fire all due tasks, advancing recurring ones first.

        Returns the dispatched run tasks (so tests can await them deterministically).
        """
        now = now or datetime.now(UTC)
        dispatched: list[asyncio.Task[None]] = []
        for task in _store.list_tasks():
            tid = task["id"]
            if tid in self._inflight:
                continue
            kind = task.get("schedule_kind") or "cron"
            tz = task.get("timezone") or self._settings.default_timezone
            nr = task.get("next_run_at")
            if not nr:
                # No next_run_at yet (freshly created, legacy row): schedule a future
                # occurrence; never fire immediately on backfill.
                with suppress(Exception):
                    self._register(task)
                continue
            nrt = _parse_iso(nr)
            if nrt is None or nrt > now:
                continue
            view = self._jobs.get(tid)
            if view is None:
                with suppress(Exception):
                    self._register(task)
                view = self._jobs.get(tid)
                if view is None:
                    continue
            if kind == "once":
                # One-shot is not advanced (completion, not advancement, governs it).
                dispatched.append(self._dispatch(tid, view))
                continue
            nxt = compute_next_run(
                kind,
                cron_expr=task.get("cron_expr"),
                interval_seconds=task.get("interval_seconds"),
                base=nrt,
                now=now,
                tz=tz,
            )
            if nxt is None:
                continue
            # Advance BEFORE executing, atomically: only the caller that wins the
            # conditional update fires this occurrence (at-most-once under overlap).
            if _store.claim_next_run(tid, expected=nr, new=_iso(nxt)):
                view.next_run_time = nxt
                dispatched.append(self._dispatch(tid, view))
        self._run_periodic_due(now)
        return dispatched

    def _run_periodic_due(self, now: datetime) -> None:
        for job_id, interval in list(self._periodic_intervals.items()):
            view = self._jobs.get(job_id)
            if view is None or view.next_run_time is None or view.next_run_time > now:
                continue
            # Re-arm before running (fast-forward whole periods if very stale), so a slow
            # or downtime-delayed periodic job does not burst.
            nxt = view.next_run_time + interval
            while nxt <= now:
                nxt += interval
            view.next_run_time = nxt
            try:
                result = view.func()
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception as exc:  # noqa: BLE001 — periodic failure is bulkheaded
                logger.warning("cron_periodic_failed id=%s error=%s", job_id, exc)

    def _dispatch(self, task_id: str, view: _JobView) -> asyncio.Task[None]:
        """Fire a due task's run under the concurrency bound, off the tick's critical path."""
        self._inflight.add(task_id)

        async def _run() -> None:
            try:
                async with self._sem:
                    result = view.func()
                    if asyncio.iscoroutine(result):
                        await result
            except Exception as exc:  # noqa: BLE001 — record via _fire; never crash the loop
                logger.warning("cron_dispatch_failed task=%s error=%s", task_id, exc)
            finally:
                self._inflight.discard(task_id)

        return asyncio.create_task(_run())

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
        task_type: str = "generate",
        notify_text: str | None = None,
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
            task_type=task_type,
            notify_text=notify_text,
        )
        self._register(task)
        self._backfill_next_run(task)
        return task

    def _backfill_next_run(self, task: dict[str, Any]) -> None:
        """Attach a human-readable next-fire hint to ``task`` for the create result.

        The next_run_at itself is computed and persisted by ``_register``; this only builds
        the echo hint. Best-effort: a failure never breaks create.
        """
        try:
            view = self._jobs.get(task["id"])
            nrt = view.next_run_time if view is not None else None
            if nrt is None:
                return
            resolved_tz = task.get("timezone") or self._settings.default_timezone
            task["next_run_at"] = _iso(nrt)
            local = nrt.strftime("%Y-%m-%d %H:%M")
            utc = nrt.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
            task["next_fire_hint"] = f" 下次触发 {local} ({resolved_tz}) / {utc} UTC"
        except Exception as exc:  # noqa: BLE001 — echo is best-effort, never break create
            logger.warning("cron_next_run_backfill_failed task=%s error=%s", task.get("id"), exc)

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
        """Terminally close a fired one-shot so it never fires again, on any outcome.

        Success (``last_status == "ok"``) flips to ``"completed"``. Failure closes
        as-is (``enabled=0``, its ``last_status``/``last_error`` preserved) — a
        failed ``once`` MUST NOT stay due for repeated automatic retries
        (fix-cron-store-and-once F2a: without this, a `once` task is never advanced,
        so its stale `next_run_at` re-fires it on every subsequent tick — an
        unbounded, un-backed-off hot retry). Manual retry remains available via
        ``run_now``.
        """
        row = _store.get(task_id)
        if row is None:
            return
        _store.set_enabled(task_id, False)
        self.remove_job(task_id)
        if row.get("last_status") == "ok":
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
        await _fire(task, connectors=connectors, history_retention=self._history_retention)
        return True

    def _register(self, task: dict[str, Any]) -> None:
        task_id = task["id"]
        tz = task.get("timezone") or self._settings.default_timezone
        kind = task.get("schedule_kind") or "cron"
        history_retention = self._history_retention

        async def _task_fire(tid: str = task_id) -> None:
            # Revalidate against the store at fire time: a row deleted or disabled by a
            # writer that bypassed the facade must never execute. The fresh row (not the
            # dict captured at registration) is the execution payload.
            row = _store.get(tid)
            if row is None or not row.get("enabled"):
                logger.warning("cron_fire_skipped task=%s reason=missing_or_disabled", tid)
                self.remove_job(tid)
                return
            connectors = self._connectors_resolver() if self._connectors_resolver else None
            await _fire(row, connectors=connectors, history_retention=history_retention)
            if (row.get("schedule_kind") or "cron") == "once":
                self._complete_once(tid)

        # Compute + persist next_run_at when the row does not carry one yet (backfill).
        nr = task.get("next_run_at")
        nrt = _parse_iso(nr) if nr else None
        if nrt is None:
            nrt = compute_next_run(
                kind,
                cron_expr=task.get("cron_expr"),
                interval_seconds=task.get("interval_seconds"),
                run_at=task.get("run_at"),
                base=None,
                now=datetime.now(UTC),
                tz=tz,
            )
            if nrt is not None:
                with suppress(Exception):
                    _store.update_run_state(task_id, next_run_at=_iso(nrt))
        self._jobs[task_id] = _JobView(func=_task_fire, next_run_time=nrt)


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
    task_type: str = "generate",
    notify_text: str | None = None,
) -> dict[str, Any]:
    """Create a task; registers the live job when a scheduler is running."""
    # Forgive the common model confusion of passing the parameter name as the kind
    # (schedule-kind-validation): `schedule_kind="run_at"` clearly means a one-shot, so
    # normalize it to "once" before the run_at normalization below. Other invalid kinds are
    # rejected by schedule_store.create.
    if schedule_kind == "run_at":
        schedule_kind = "once"
    # Normalize a one-shot run_at to canonical ISO at write time (cron-runat-hardening) so the
    # store never holds a form the parser later chokes on. Reuses the single parser; an
    # unparseable run_at raises ValueError here (the schedule tool surfaces it as clean text).
    # A naive run_at is interpreted in the task's resolved timezone (explicit > live
    # scheduler's deployment default > static UTC fallback) — never the host process's
    # system timezone (fix-cron-store-and-once F3).
    if schedule_kind == "once" and run_at:
        sched = current()
        sched_settings = getattr(sched, "_settings", None)  # noqa: SLF001
        resolved_tz = (
            timezone
            or getattr(sched_settings, "default_timezone", None)
            or SchedulingSettings().default_timezone
        )
        run_at = _parse_run_at(run_at, tz=resolved_tz).isoformat()
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
        "task_type": task_type,
        "notify_text": notify_text,
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


def list_runs(task_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Read-only passthrough of a task's recent run history for the tool layer."""
    return _store.list_runs(task_id, limit=limit)


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
