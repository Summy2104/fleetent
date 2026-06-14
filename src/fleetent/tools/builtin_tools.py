"""Built-in tools. Import this module to register them with the tool registry."""

import asyncio
import datetime
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from fleetent import eval_logger
from fleetent.integrations.sandbox import (
    BaseSandboxBackend,
    ExecResult,
    SandboxManager,
    build_sandbox_env,
    cap_or_spill,
    redact_secrets,
)
from fleetent.integrations.sandbox import output_truncation as sot
from fleetent.runtime.cancellation import CancelToken
from fleetent.runtime.error_classifier import (
    CLASSIFICATION_TABLE,
    ErrorCategory,
    ErrorClassification,
)
from fleetent.tools import image_gen_client, vision_client
from fleetent.tools.registry import ToolContext, tool

logger = logging.getLogger(__name__)

# How often the cancel watcher polls the token while exec runs (seconds). Small
# enough that cancellation is observed promptly, large enough to stay cheap.
_CANCEL_POLL_INTERVAL = 0.05

# Returned (not raised) when a sandbox exec exceeds its exec_timeout deadline (SB7),
# so the conversation can continue. Distinct from the external-cancel text.
_SANDBOX_TIMEOUT_TEXT = "沙箱执行超时：代码执行超过沙箱时限，容器已被强制终止。"


def _sandbox_timeout_classification() -> ErrorClassification:
    """Read AR5's sandbox_timeout classification directly (SB7 D3).

    The timeout→category decision is the sandbox's own domain knowledge; we then
    consume AR5's read-only flags straight from CLASSIFICATION_TABLE rather than
    calling classify() (which only recognizes APIStatusError).
    """
    return CLASSIFICATION_TABLE[ErrorCategory.sandbox_timeout]


# Process-wide sandbox lifecycle manager (SB2). Lazily built on first run_code so
# config is read once, not per call; injectable (tests monkeypatch this to an
# isolated instance) rather than a hidden global — the registry lives on the
# instance, not at module scope.
_MANAGER: SandboxManager | None = None


def _get_manager() -> SandboxManager:
    global _MANAGER
    if _MANAGER is None:
        from fleetent.integrations.sandbox.factory import create_backend

        _MANAGER = SandboxManager(backend=create_backend())
    return _MANAGER


def init_sandbox_manager(agent: object | None = None) -> SandboxManager:
    """(Re)build the process sandbox manager with the agent-selected backend.

    Called by the agent runtime at startup so a standalone agent's `agent.yaml`
    `sandbox.backend` override takes effect (factory precedence: agent > platform >
    docker). `agent` is an `AgentFile`; typed loosely to avoid a runtime import cycle.
    """
    global _MANAGER
    from fleetent.agent_config import AgentFile
    from fleetent.integrations.sandbox import SkillMountConfig
    from fleetent.integrations.sandbox.factory import create_backend

    resolved = agent if isinstance(agent, AgentFile) else None
    skill_mount = None
    image_persistence = False
    setup_command: str | None = None
    # Multi-user run-shape signal (sandbox-multi-user-default). Fail-safe: default True
    # even with no AgentFile, so the manager's guard correcting a configured `agent`
    # workspace_scope to `session` is always live (a single-process one-shot is session
    # regardless, so this is harmless there). A configured AgentFile carries its own
    # `sandbox.multi_user` (itself defaulting True; explicit false opts a single-user
    # deployment out). Carried via config to keep the runtime free of platform knowledge.
    multi_user = True
    if resolved is not None:
        # Per-agent override of the skills bind-mount (sandbox-skill-mount); None lets
        # the manager fall back to the platform `sandbox.skill_mount` defaults.
        sm = resolved.sandbox.skill_mount
        skill_mount = SkillMountConfig(enabled=sm.enabled, read_only=sm.read_only, source=sm.source)
        # Per-agent dependency-image persistence (sandbox-image-persistence): an
        # independent switch from workspace_scope. Default off keeps prior behaviour.
        image_persistence = resolved.sandbox.image_persistence
        setup_command = resolved.sandbox.setup_command
        multi_user = resolved.sandbox.multi_user
    _MANAGER = SandboxManager(
        backend=create_backend(resolved),
        skill_mount=skill_mount,
        image_persistence=image_persistence,
        setup_command=setup_command,
        multi_user=multi_user,
    )
    return _MANAGER


# Workspace-relative subdirectories for image products (sandbox-workspace-root).
# Both live under the per-scope `/workspace` (= host workspace dir), so the model
# sees a single root and references flow as workspace-relative paths that resolve to
# the same physical file in container and host-degrade modes.
_GENERATED_SUBDIR = "generated"
_UPLOADS_SUBDIR = "uploads"

# Map common image mimes to file extensions for stored uploads.
_MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _workspace_root_for(tool_context: ToolContext | None) -> Path:
    """Resolve the per-scope host workspace dir for the current tool context (D6).

    Reuses the manager's single `workspace_host_path` resolution point so generated/
    uploaded products land in the very directory `run_code` / file tools are fenced
    to (container `/workspace` = this host dir). Degrades to the run_code default key
    when called without a context, mirroring run_code's own fallback so the workspace
    key matches.
    """
    manager = _get_manager()
    session_id = (
        tool_context.session_id
        if tool_context is not None and tool_context.session_id
        else "run-code"
    )
    agent_name = tool_context.agent_name if tool_context is not None else None
    return manager.workspace_host_path(manager.scope, session_id, agent_name or "default")


def _workspace_scope_and_root(tool_context: ToolContext | None) -> tuple[object, Path]:
    """Return ``(manager.scope, host workspace dir)`` for the current tool context.

    Used by send_file to gate on workspace scope while reusing the same single
    `workspace_host_path` resolution point (so the resolved dir is exactly the one
    run_code / file tools are fenced to). Kept out of the tool body so the
    sole-sandbox-consumer guard (run_code only) is not tripped by send_file.
    """
    manager = _get_manager()
    session_id = (
        tool_context.session_id
        if tool_context is not None and tool_context.session_id
        else "run-code"
    )
    agent_name = (tool_context.agent_name if tool_context is not None else None) or "default"
    return manager.scope, manager.workspace_host_path(manager.scope, session_id, agent_name)


def _save_image(data: bytes, tool_context: ToolContext | None = None) -> str:
    """Write image bytes to the per-scope workspace `generated/` and return a relative ref.

    The reference is the workspace-relative `generated/<uuid>.png` (never base64, never
    a host-absolute path), so the model stays in the single `/workspace` world and the
    file is readable via file tools / run_code by the same relative path.
    """
    root = _workspace_root_for(tool_context)
    generated = root / _GENERATED_SUBDIR
    generated.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.png"
    (generated / name).write_bytes(data)
    return f"{_GENERATED_SUBDIR}/{name}"


def _save_upload(data: bytes, mime: str, tool_context: ToolContext | None = None) -> str:
    """Write inbound image bytes to the per-scope workspace `uploads/`, return a relative ref.

    Aligns with `normalizer._save_file_to_workspace`: the reference is the
    workspace-relative `uploads/<uuid>.<ext>` (never base64, never host-absolute), and
    analyze_image reads the bytes back via this same relative reference.
    """
    root = _workspace_root_for(tool_context)
    uploads = root / _UPLOADS_SUBDIR
    uploads.mkdir(parents=True, exist_ok=True)
    ext = _MIME_EXT.get(mime, ".bin")
    name = f"{uuid.uuid4().hex}{ext}"
    (uploads / name).write_bytes(data)
    return f"{_UPLOADS_SUBDIR}/{name}"


def _read_upload(ref: str, tool_context: ToolContext | None = None) -> bytes:
    """Read image bytes from an uploads reference, via workspace resolution (D6).

    A workspace-relative ref (`uploads/<name>.png`) resolves under the per-scope host
    workspace dir (= container `/workspace`, same physical file in both modes). A
    legacy host-absolute ref (from a pre-migration session) is read directly as a
    backward-compatibility fallback so historical references keep working.
    """
    if os.path.isabs(ref):
        return Path(ref).read_bytes()
    root = _workspace_root_for(tool_context)
    return (root / ref).read_bytes()


@tool
def get_current_time() -> str:
    """Return the current UTC time as a string."""
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


@tool
def calculate(expression: str) -> str:
    """Evaluate a basic arithmetic expression and return the result."""
    allowed = set("0123456789+-*/()., ")
    if not all(c in allowed for c in expression):
        return "error: only arithmetic expressions are allowed"
    try:
        result = eval(expression)  # noqa: S307  # whitelist-validated above
        return str(result)
    except Exception as exc:
        return f"error: {exc}"


@tool
def whoami(tool_context: ToolContext | None = None) -> str:
    """Return the current requester's identity and conversation context.

    Use when you need to know who is talking to you (platform user id + name),
    where (DM vs which channel), or the current time. Reads the inbound message's
    session context; returns "未知" fields when unavailable (e.g. a CLI run with no
    IM context). Never raises.
    """
    sc = getattr(tool_context, "session_context", None) if tool_context else None
    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    if sc is None:
        return f"发起人: 未知 (无 IM 上下文)\n当前时间: {now}"

    def _g(attr: str) -> str:
        return str(getattr(sc, attr, "") or "未知")

    scene = "私信 (DM)" if _g("chat_type") == "dm" else f"频道 {_g('channel_name')}"
    return (
        f"平台: {_g('platform')}\n"
        f"发起人 ID: {_g('sender_id')}\n"
        f"发起人名称: {_g('sender_name')}\n"
        f"场景: {scene}\n"
        f"当前时间: {now}"
    )


@tool
def read_skill(name: str, tool_context: ToolContext | None = None) -> str:
    """Read a skill's full instructions by name (from the <available_skills> list).

    When a skill in the available_skills catalog matches the task, call this with
    its <name> to load the full SKILL.md, then follow it. Returns an error string
    if no skill with that name is registered, or a refusal if the skill failed the
    static injection audit (its content never reaches the model this way).
    """
    from fleetent.skills import registry as skill_registry

    entry = skill_registry._index.get(name)
    if entry is None:
        return f"error: no skill named {name!r}"
    if entry.audit_blocked:
        # Refuse before load(): a severe injection hit means the body must not
        # reach the model. load() itself still returns it for manual triage.
        _audit_skill_refusal(name, tool_context)
        return f"error: skill {name!r} was blocked by the static injection audit"
    body = skill_registry.load(name)
    _record_skill_hit(name, tool_context)
    # Append the fixed exec-face / $SKILLS_DIR guidance so the model runs the skill's
    # scripts via run_code under the single /workspace world (skill-read-on-demand).
    return body + skill_registry._READ_SKILL_GUIDANCE


def _record_skill_hit(name: str, tool_context: ToolContext | None) -> None:
    """Record a successful read_skill load as an agent-side observability trace event.

    Best-effort: a recording failure (DB unavailable, etc.) is logged and swallowed so it
    never blocks returning the skill body. Writes to the agent's observability trace —
    never to a platform store (agent/platform decoupling); the platform reads per-skill
    metrics from the trace.
    """
    from fleetent.observability.traces import TraceEvent, record_trace_event

    agent_name = tool_context.agent_name if tool_context else None
    session_id = tool_context.session_id if tool_context else None
    try:
        record_trace_event(
            TraceEvent(
                run_id=session_id or "",
                event_type="skill_hit",
                payload={"skill_name": name},
                session_id=session_id,
                agent_name=agent_name,
            )
        )
    except Exception as exc:  # noqa: BLE001 — observability is a side channel; never block
        logger.warning("skill_hit_record_failed", extra={"skill": name, "error": str(exc)})


def _audit_skill_refusal(name: str, tool_context: ToolContext | None) -> None:
    """Record a read_skill refusal of an audit_blocked skill (skill-read-refusal-audit).

    Best-effort: the refusal is the security guarantee; a failure of this side-channel
    audit write must never change the refusal outcome (logged, then swallowed).
    """
    from fleetent import audit_log

    detail = {
        "reason": "audit_blocked",
        "session_id": tool_context.session_id if tool_context else None,
        "agent_name": tool_context.agent_name if tool_context else None,
    }
    try:
        audit_log.write_audit(None, "skill.read_refused", "skill", name, detail=detail)
    except Exception as exc:  # noqa: BLE001 — audit is a side channel; never block the refusal
        logger.warning("skill_read_refusal_audit_failed", extra={"skill": name, "error": str(exc)})


# read_file and write_file have moved to file_tools.py.
# Re-exported here so existing imports remain unbroken.
from fleetent.tools.file_tools import read_file as read_file  # noqa: F401,E402
from fleetent.tools.file_tools import write_file as write_file  # noqa: F401,E402


async def _exec_or_cancel(
    client: BaseSandboxBackend,
    ws_id: str,
    command: str,
    cancel_token: CancelToken,
    session_id: str | None = None,
) -> ExecResult | None:
    """Run exec, aborting if the token cancels or its deadline passes.

    Returns the ExecResult on normal completion, or None when cancellation (or a
    passed deadline) is observed first — in which case the container is terminated
    gracefully (SB7: SIGTERM → grace → SIGKILL) and then removed, rather than left
    hanging on a blocked exec. The caller distinguishes timeout from external
    cancel by whether the token's own deadline has passed. `session_id` enables
    session-snapshot continuity (cwd defaults to the mounted /workspace).
    """
    exec_task = asyncio.create_task(client.exec(ws_id, command, session_id=session_id))
    while True:
        if cancel_token.is_cancelled():
            exec_task.cancel()
            await asyncio.gather(exec_task, return_exceptions=True)
            # SB7: terminate the container process gracefully (SIGTERM → SIGKILL)
            # rather than the violent rm -f, then remove it (idempotent) so the
            # registry forget below cannot collide with a lingering stopped name.
            await client.kill_workspace(ws_id)
            await client.destroy_workspace(ws_id)
            return None
        done, _ = await asyncio.wait({exec_task}, timeout=_CANCEL_POLL_INTERVAL)
        if exec_task in done:
            return exec_task.result()


# /exchange/<server_id>/<rel> references embedded in run_code source (staging fallback).
_EXCHANGE_REF_RE = re.compile(r"/exchange/[A-Za-z0-9_.-]+/[^\s\"'<>),;]+")


async def _stage_exchange_refs(
    code: str, scope_key: str | None, backend: BaseSandboxBackend, ws_id: str
) -> int:
    """Stage attribution-passing /exchange refs into the container (D5 degrade, §4.7/4.8).

    No-op on `exchange_mount`-capable backends (the ro view mount handles it). Otherwise the
    `/exchange/...` paths literally referenced in the code are resolved through
    artifact_exchange (own-scope only; cross-scope / unregistered are silently skipped — not
    staged) and copied into the container before exec. Returns the count staged; logs a
    degrade line when refs were present. Best-effort: a copy failure is logged, never raised.
    """
    if getattr(backend.capabilities, "exchange_mount", False):
        return 0
    refs = sorted(set(_EXCHANGE_REF_RE.findall(code)))
    if not refs:
        return 0
    from fleetent import artifact_exchange

    staged = 0
    for ref in refs:
        try:
            host = artifact_exchange.resolve(ref, scope_key, approved=False)
        except Exception:  # noqa: BLE001 — cross-scope/unregistered/gone → not staged
            continue
        try:
            await backend.stage_file(ws_id, ref, host.read_bytes())
            staged += 1
        except Exception as exc:  # noqa: BLE001 — staging is best-effort, never break exec
            logger.warning("exchange_staging_copy_failed ref=%s error=%s", ref, exc)
    logger.warning(
        "exchange_staging_degrade backend=%s refs=%d staged=%d",
        getattr(backend, "name", "?"),
        len(refs),
        staged,
    )
    return staged


@tool(risk_level="medium", self_truncates=True)
async def run_code(
    code: str,
    cancel_token: CancelToken | None = None,
    tool_context: ToolContext | None = None,
) -> str:
    """Execute Python code in an isolated Docker container and return the output.

    The container has no network access and limited memory (256 MB).
    State does not persist between calls.
    """
    token = cancel_token if cancel_token is not None else CancelToken()
    manager = _get_manager()
    # SB3 D5: key the workspace on the context's session id so SB2 can locate/reuse
    # it; degrade to the default key when called without a context (direct/unbound
    # call) — never raise here. agent_name feeds agent-scope naming.
    session_id = (
        tool_context.session_id
        if tool_context is not None and tool_context.session_id
        else "run-code"
    )
    agent_name = tool_context.agent_name if tool_context is not None else None
    scope = manager.scope
    # SB5 D4: the only injection source is the agent's predeclared
    # `features.sandbox_env`; build_sandbox_env filters sensitive names (and host
    # env is not passed). runtime_env is left unwired — no AI/user-supplied env.
    features = tool_context.features if tool_context is not None else {}
    agent_env = features.get("sandbox_env")
    env = build_sandbox_env(agent_env=agent_env)
    ws_id = await manager.acquire(scope, session_id, agent_name or "default", env=env)
    # unified-file-exchange §4.7/4.8: on a backend without exchange_mount, stage the code's
    # attribution-passing /exchange refs into the container before exec (no-op on capable
    # backends, where the ro view mount already exposes them). Best-effort, never breaks run.
    try:
        scope_key = getattr(tool_context, "scope_key", None)
        await _stage_exchange_refs(code, scope_key, manager.backend, ws_id)
    except Exception as exc:  # noqa: BLE001 — staging is auxiliary, never break run_code
        logger.warning("exchange_staging_failed error=%s", exc)
    command = f"python3 -c {__import__('shlex').quote(code)}"
    # SB2 D4: normal completion does NOT destroy — reuse is the point; destruction
    # is owned by release_session / sweep_idle. AR19's cancel path still hard-aborts
    # by destroying the container; we then drop the registry entry so a later acquire
    # rebuilds (find_workspace miss) rather than handing back a destroyed container.
    # SB9 D4: time only the exec (not container acquisition); container-lifecycle
    # timing is SB2's concern. exit_code / byte sizes come from the ExecResult.
    # SB7: merge the sandbox exec_timeout deadline with the external token via the
    # AR20 `parent` link, so a single token reflects "own timeout OR external/parent
    # cancel". On trigger we tell the two apart by whether this child's own deadline
    # has passed (timeout) or not (external cancel) — mirrors AR20's timed_out vs
    # cancelled split.
    exec_timeout = manager.resources_for(scope).exec_timeout
    start = time.monotonic()
    child = CancelToken(deadline=start + exec_timeout, parent=token)
    result = await _exec_or_cancel(manager.backend, ws_id, command, child, session_id=session_id)
    if result is not None and manager.backend.is_workspace_missing(result):
        # Container died between acquire and exec (sandbox-liveness-reacquire):
        # drop the stale registration, rebuild on the same host-mounted workspace,
        # retry exactly once instead of surfacing an infrastructure error.
        manager.invalidate(scope, session_id, agent_name or "default")
        ws_id = await manager.acquire(scope, session_id, agent_name or "default", env=env)
        result = await _exec_or_cancel(
            manager.backend, ws_id, command, child, session_id=session_id
        )
    elapsed = time.monotonic() - start
    if result is None:
        manager.forget(manager.container_name(scope, session_id, agent_name or "default"))
        # Cancelled/timed-out exec yields no ExecResult; skip the trace rather than
        # log placeholder metadata. Distinguish sandbox timeout from external cancel.
        if child.deadline is not None and time.monotonic() >= child.deadline:
            classification = _sandbox_timeout_classification()  # AR5 sandbox_timeout (D3)
            logger.warning(
                "sandbox_exec_timeout container=%s category=%s should_retry=%s",
                ws_id[:12],
                ErrorCategory.sandbox_timeout.value,
                classification.should_retry,
            )
            return _SANDBOX_TIMEOUT_TEXT
        return "code execution cancelled"
    # SB9 D3: trace is side-channel observability; a write failure MUST NOT block
    # the user from receiving the execution result. Catch + warn, never re-raise.
    try:
        eval_logger.log_sandbox_exec(
            elapsed_s=elapsed,
            exit_code=result.exit_code,
            stdout_bytes=len(result.stdout.encode("utf-8")),
            stderr_bytes=len(result.stderr.encode("utf-8")),
            sandbox_scope=scope.value,
            agent_name=agent_name,
        )
    except Exception:
        logger.warning("sandbox_exec trace write failed", exc_info=True)
    # SB6: cap each stream for the AI-facing result (trace above kept original
    # bytes). stdout/stderr have independent budgets. run_code is exempt from T4
    # (declared self_truncates) so this is the sole truncation of its output.
    # sandbox-output-redaction: redact secrets BEFORE capping so a secret straddling
    # the boundary cannot survive, and so anything spilled to disk is already redacted.
    # sandbox-large-output-spill: over-budget output is spilled to a file (full, redacted)
    # and replaced with a preview + reference, rather than dropping the middle. The trace
    # byte sizes above stay on the original (un-redacted) output as a pure volume metric.
    parts = []
    stdout = cap_or_spill(redact_secrets(result.stdout), sot.MAX_STDOUT_BYTES, label="stdout")
    if stdout:
        parts.append(stdout.rstrip())
    stderr = cap_or_spill(redact_secrets(result.stderr), sot.MAX_STDERR_BYTES, label="stderr")
    if stderr:
        parts.append(f"[stderr] {stderr.rstrip()}")
    if result.exit_code != 0:
        parts.append(f"[exit {result.exit_code}]")
    return "\n".join(parts) if parts else "(no output)"


def _origin_from_context(tool_context: ToolContext | None) -> dict[str, str | None] | None:
    """Build a scheduled-task `origin` from the inbound IM context, or None.

    Captures the creation chat so a fired reminder defaults back to where it was
    created (delivery resolves `origin` when no explicit `deliver` is set). The
    chat id is the connector's channel id (Slack channel/DM id, Telegram chat id),
    posted back via the channel path so the original thread is preserved.
    """
    sc = getattr(tool_context, "session_context", None) if tool_context else None
    platform = getattr(sc, "platform", None) if sc else None
    chat_id = getattr(sc, "channel_name", None) if sc else None
    if not platform or not chat_id:
        return None
    return {
        "platform": platform,
        "chat_id": chat_id,
        "target_type": "channel",
        "thread_id": getattr(sc, "thread_root", None) or None,
    }


@tool(risk_level="low")
async def schedule(
    action: str,
    name: str = "",
    schedule_kind: str = "cron",
    cron_expr: str = "",
    run_at: str = "",
    interval_seconds: int = 0,
    message: str = "",
    timezone: str = "UTC",
    user_id: str = "default",
    task_id: str = "",
    notify_platform: str = "",
    notify_target: str = "",
    notify_target_type: str = "user",
    task_type: str = "generate",
    notify_text: str = "",
    tool_context: ToolContext | None = None,
) -> str:
    """Manage scheduled tasks. ``action`` is one of create/list/remove/run_now/pause/resume.

    create: schedule_kind=cron (cron_expr like '0 9 * * 1-5'), once (run_at: ISO time or
    a relative duration like '+30m'), or interval (interval_seconds). Deliver target:
    notify_platform/notify_target (target_type user|channel); else defaults to the chat the
    task was created in.

    Pick task_type by asking: **does the message content need information only known at send
    time?**
    - No, fixed wording → ``task_type="notify"``: provide the final polished copy in
      ``notify_text`` (NOT message). At creation time, refine the user's rough wording into
      the final copy, echo it back for confirmation, then create — at fire time the scheduler
      sends ``notify_text`` verbatim, no model run.
    - Yes, content made at fire time (summaries, fresh data) → ``task_type="generate"`` (default):
      put the instruction in ``message``; your fired reply IS what gets posted.
    - The task performs actions (send DMs/files, conditional/multi-target) → ``task_type="action"``:
      put the instruction in ``message``; you act via your own tools and the scheduler does
      NOT broadcast your reply.

    pause/resume toggle a task; remove deletes it; run_now fires it immediately; list shows all.
    """
    from fleetent import cron_scheduler

    if action == "create":
        deliver = None
        if notify_platform and notify_target:
            deliver = {
                "mode": "explicit",
                "platform": notify_platform,
                "target": notify_target,
                "target_type": notify_target_type,
            }
        origin = _origin_from_context(tool_context)
        # Owner = who is acting (resolved principal), never what the model typed;
        # the user_id parameter is only a fallback for principal-less runs.
        ctx_principal = getattr(tool_context, "principal", None) if tool_context else None
        owner = ctx_principal.user_id if ctx_principal is not None else user_id
        try:
            task = cron_scheduler.create_task(
                name=name,
                cron_expr=cron_expr or None,
                timezone=timezone,
                user_id=owner,
                message=message,
                source="tool",
                schedule_kind=schedule_kind,
                run_at=run_at or None,
                interval_seconds=interval_seconds or None,
                origin=origin,
                deliver=deliver,
                task_type=task_type,
                notify_text=notify_text or None,
            )
        except ValueError as exc:
            # Per-type validation (e.g. notify without notify_text/target) → clean text,
            # never a raised exception the agent loop would have to recover from.
            return f"error: {exc}"
        if cron_scheduler.current() is None:
            # No live scheduler in this process — be truthful so the AI does not
            # promise the user a fire time that will never come.
            return (
                f"Scheduled task saved: id={task['id']!r} name={name!r} "
                f"kind={schedule_kind!r} — takes effect when the agent service is running "
                "(no scheduler in this process)"
            )
        return (
            f"Scheduled task created and registered: id={task['id']!r} "
            f"name={name!r} kind={schedule_kind!r}"
        )

    if action == "list":
        tasks = cron_scheduler.list_tasks(include_disabled=True)
        if not tasks:
            return "No scheduled tasks"
        lines = [
            f"{t['id']} | {t.get('name')} | {t.get('schedule_kind')} | "
            f"{'enabled' if t.get('enabled') else 'paused'}"
            for t in tasks
        ]
        return "\n".join(lines)

    if action == "remove":
        deleted = cron_scheduler.remove_task(task_id)
        if not deleted:
            return f"error: task {task_id!r} not found"
        return f"Scheduled task {task_id!r} removed"

    if action in ("pause", "resume"):
        matched = cron_scheduler.set_task_enabled(task_id, action == "resume")
        if not matched:
            return f"error: task {task_id!r} not found"
        return f"Scheduled task {task_id!r} {action}d"

    if action == "run_now":
        fired = await cron_scheduler.run_task_now(task_id)
        if not fired:
            return f"error: task {task_id!r} not found"
        return f"Scheduled task {task_id!r} fired"

    return f"error: unknown action {action!r} (use create/list/remove/run_now/pause/resume)"


@tool(risk_level="low")
async def generate_image(
    prompt: str, size: str = "", tool_context: ToolContext | None = None
) -> str:
    """Generate an image from a text prompt via the self-hosted images endpoint.

    Returns a workspace-relative reference (`generated/<name>.png`) to the saved
    image, never inline base64 or a host-absolute path. On endpoint failure/timeout,
    returns an explicit error result for the AI to handle rather than raising and
    breaking the loop.
    """
    try:
        data = await image_gen_client.generate(prompt, size=size or None)
    except image_gen_client.ImageGenError as exc:
        return f"error: image generation failed: {exc}"
    ref = _save_image(data, tool_context)
    return f"image generated: {ref}"


@tool(risk_level="low")
async def analyze_image(ref: str, instruction: str, tool_context: ToolContext | None = None) -> str:
    """Understand an image on demand via the self-hosted vision endpoint.

    `ref` is a stored-image reference (a workspace-relative `uploads/<name>` produced
    when an inbound image was saved; legacy host-absolute refs still resolve);
    `instruction` is what to look for (e.g. "read the invoice total"). Returns a
    structured text description, never inline base64. Use this to re-examine or
    compare images already in the conversation. On invalid ref, unconfigured
    endpoint, or endpoint failure, returns an explicit error result for the AI to
    handle rather than raising and breaking the loop.
    """
    try:
        data = _read_upload(ref, tool_context)
    except OSError as exc:
        return f"error: cannot read image reference {ref!r}: {exc}"
    try:
        return await vision_client.analyze(data, instruction)
    except vision_client.VisionError as exc:
        return f"error: image analysis failed: {exc}"


@tool
def sub_agent(tasks: str) -> str:
    """Run multiple sub-tasks in parallel. tasks is a JSON array with 'name' and 'prompt' fields."""
    # Execution is intercepted by agent_loop before reaching here.
    return "sub_agent must be called through the agent loop"


@tool(risk_level="medium")
async def invoke_agent(
    agent_name: str, message: str, tool_context: ToolContext | None = None
) -> str:
    """Delegate a message to another named agent and return its reply."""
    # Lazy import: the loop imports tools at module load (circular otherwise).
    from fleetent.runtime import load_active
    from fleetent.runtime import loop as agent_loop

    snapshot = load_active(agent_name)
    if snapshot is None:
        return f"agent {agent_name!r} not found"
    messages = [
        {"role": "system", "content": snapshot.system_prompt},
        {"role": "user", "content": message},
    ]
    # Identity-port「继承」: forward the current turn's Principal to the called agent
    # so the internal call is not principal-less (tenant_id stays bound, no re-auth).
    principal = getattr(tool_context, "principal", None) if tool_context else None
    # Parameter-style run (next<-main integration chose params over snapshot): the
    # system prompt rides in `messages`; pass the snapshot's allowlist + name through.
    return await agent_loop.run(
        messages,
        principal=principal,
        is_sub_agent=True,
        allowed_tools=snapshot.allowed_tools,
        agent_name=agent_name,
        model_policy=snapshot.model_policy,
    )


@tool(risk_level="medium")
async def send_im_message(
    target: str,
    text: str,
    target_type: str = "user",
    platform: str = "",
    files: list[str] | None = None,
    tool_context: ToolContext | None = None,
) -> str:
    """Proactively send an IM message — optionally with file attachments — to a user/channel.

    Use when the user asks you to notify or message someone, or to post to a
    channel — beyond replying in the current conversation (replying needs no
    tool). `target` is the platform-native id (Slack `U…`/`C…`, Telegram chat
    id); `target_type` is "user" for a DM (default) or "channel" for a channel
    post. `platform` defaults to the current conversation's platform. `files` is an
    optional list of workspace-relative or `/exchange/<server_id>/...` paths to attach
    (this tool is always approval-gated, so the approval authorizes cross-scope artifacts).
    """
    # Lazy import: keeps module load light and avoids cycles (builtin convention).
    from fleetent import outbound

    connectors = tool_context.outbound_connectors if tool_context else {}
    sc = getattr(tool_context, "session_context", None) if tool_context else None
    resolved_platform = platform or str(getattr(sc, "platform", "") or "")
    if not resolved_platform:
        return "发送失败：未指定平台且当前会话无平台信息，请显式传入 platform。"
    connector = connectors.get(resolved_platform)
    if connector is None:
        return (
            f"发送失败：当前通道不支持主动外发（无可用 {resolved_platform} 连接器）。"
            "该功能仅在 IM 网关运行时可用。"
        )
    if target_type == "user":
        reachable = await outbound.is_reachable(resolved_platform, connector, target)
        if not reachable:
            return (
                f"发送失败：目标 {target} 在 {resolved_platform} 上不可达/无法触达"
                "（Telegram 用户需先与 bot 对话过）。"
            )
    sent = await outbound.send_to(
        resolved_platform, connector, target, text, target_type=target_type
    )
    if not sent:
        return f"发送失败：{resolved_platform} 投递 {target} 时出错，请稍后重试。"
    kind = "私信" if target_type == "user" else "频道消息"

    # Attachments (§7): resolve each through the shared kernel (approved=True — this tool is
    # always medium-gated, so the approval authorizes cross-scope artifacts). Per-file
    # degrade: a bad/cross-scope-gone entry is skipped with a note, never aborting the send.
    delivered, skipped = 0, []
    for raw in files or []:
        try:
            host = _resolve_outbound_path(raw, tool_context, approved=True)
            ok = await outbound.send_file_to(resolved_platform, connector, target, str(host))
        except Exception as exc:  # noqa: BLE001 — per-file degrade, never abort the batch
            skipped.append(f"{raw}（{exc}）")
            continue
        if ok:
            delivered += 1
        else:
            skipped.append(f"{raw}（投递失败）")

    result = f"已发送{kind}到 {resolved_platform}:{target}。"
    if files:
        result += f" 附件 {delivered}/{len(files)} 已投递。"
        if skipped:
            result += " 跳过：" + "；".join(skipped)
    return result


def _resolve_outbound_path(path: str, tool_context: Any, *, approved: bool) -> Path:
    """Resolve a send path to a host file across both roots — the shared delivery kernel.

    Workspace-relative paths resolve via the same fence the file tools use; `/exchange`
    paths resolve through the ledger with attribution (``approved`` bypasses the scope
    check — send_file passes True because the gate already vetted it; send_im_message
    passes True because it is always medium-gated, so a human approval authorizes the
    cross-scope delivery). Raises ValueError / ExchangeResolutionError / FileNotFoundError.
    """
    from fleetent.tools.file_sandbox_io import resolve_host_path
    from fleetent.tools.file_tools import _is_exchange_path

    if _is_exchange_path(path):
        from fleetent import artifact_exchange

        scope_key = getattr(tool_context, "scope_key", None)
        return artifact_exchange.resolve(path, scope_key, approved=approved)
    _scope, root = _workspace_scope_and_root(tool_context)
    host = resolve_host_path(root, path)
    if not host.is_file():
        raise FileNotFoundError(f"workspace 内不存在文件 {path!r}（请确认已写入）")
    return host


def _send_file_risk(args: dict[str, Any], tool_context: Any) -> str:
    """Call-time risk for send_file (D6/D7): low iff the box is closed, else medium.

    Low (no-approval) requires all of: an interactive `session_context` (recipient is
    harness-fixed) ∧ a DM conversation ∧ the file owned by the current run's scope
    (workspace-relative is always this run's scope; an `/exchange` artifact must resolve
    under the run's scope_key). Any miss escalates to medium approval — replacing the old
    fail-closed decline so every dead end becomes "at worst one approval click". A missing
    session_context returns medium; the body still fail-closes (no recipient / approval loop).
    """
    sc = getattr(tool_context, "session_context", None) if tool_context else None
    if sc is None:
        return "medium"
    if str(getattr(sc, "chat_type", "") or "") != "dm":
        return "medium"
    path = str(args.get("path", "") or "")
    from fleetent.tools.file_tools import _is_exchange_path

    if _is_exchange_path(path):
        from fleetent import artifact_exchange

        scope_key = getattr(tool_context, "scope_key", None)
        try:
            artifact_exchange.resolve(path, scope_key, approved=False)
            return "low"  # own-scope artifact
        except Exception:  # noqa: BLE001 — cross-scope / unregistered / gone → escalate
            return "medium"
    return "low"  # workspace-relative path is always the current run's scope


@tool(risk_level=_send_file_risk)
async def send_file(path: str, tool_context: ToolContext | None = None) -> str:
    """Send a product file back to the current conversation's sender.

    Use this to deliver a file to the person you are talking with. `path` is either a
    **workspace-relative** path (the `/workspace` root) or an **`/exchange/<server_id>/...`**
    canonical path (a file an MCP tool produced). It is resolved to the real host file and
    sent as an attachment. The recipient is fixed to the current sender — you cannot specify
    one. A DM with files owned by this run sends directly; anything else (a channel, a
    cross-scope artifact) goes through a one-time approval rather than failing.
    """
    # Recipient is harness-fixed from session_context; the model cannot supply it. No
    # session_context = no recipient / no approval loop (scheduled task / sub_agent) → decline.
    sc = getattr(tool_context, "session_context", None) if tool_context else None
    if sc is None:
        return (
            "无法发送：当前运行路径无会话发起人，无法自动外发文件"
            "（如 scheduled task / sub_agent）。"
        )

    # Escalation (channel / cross-scope) is enforced by the callable risk (_send_file_risk)
    # + permission gate; by the time the body runs the call is either low or approved. The
    # shared kernel resolves with approved=True (the gate already vetted attribution).
    try:
        host_path = _resolve_outbound_path(path, tool_context, approved=True)
    except (ValueError, FileNotFoundError) as exc:
        return f"无法发送：{exc}"

    platform = str(getattr(sc, "platform", "") or "")
    recipient = str(getattr(sc, "sender_id", "") or "")
    connectors = tool_context.outbound_connectors if tool_context else {}
    connector = connectors.get(platform)
    if connector is None:
        return (
            f"当前通道不支持主动外发文件（无可用 {platform or '?'} 连接器）。"
            "该功能仅在 IM 网关运行时可用。"
        )

    # Lazy import: keeps module load light and avoids cycles (builtin convention).
    from fleetent import outbound

    try:
        sent = await outbound.send_file_to(platform, connector, recipient, str(host_path))
    except Exception as exc:  # noqa: BLE001 — outbound must never abort the agent run
        logger.warning("send_file delivery error on %s: %s", platform, exc)
        return f"外发失败：{platform} 投递文件时出错，请稍后重试。"
    if not sent:
        return f"外发失败：{platform} 投递文件给 {recipient} 时出错，请稍后重试。"
    return f"已把文件发送给 {platform}:{recipient}。"
