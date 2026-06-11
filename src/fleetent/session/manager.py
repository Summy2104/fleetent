from __future__ import annotations

import asyncio
import json
import shutil
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fleetent import paths
from fleetent.structured_logging import get_logger

_logger = get_logger("session.manager")

# Tool results larger than this are externalized to a sibling .tool_outputs dir so
# the session JSON and the model context stay lean (tool-result-extern, cf claude-code).
_TOOL_RESULT_INLINE_LIMIT = 50 * 1024
_STORED_PREFIX = "[stored:"
_STORED_SUFFIX = ".txt]"

# Cross-process file lock primitive (P0-4). POSIX-only; non-POSIX platforms (Windows)
# degrade to in-process asyncio.Lock alone. fleetent targets Linux deployment.
try:
    import fcntl

    _flock_available = True
except ImportError:  # pragma: no cover — non-POSIX fallback
    fcntl = None  # type: ignore[assignment]
    _flock_available = False
    _logger.warn("session_flock_unavailable_degraded_to_asyncio_lock")

SESSIONS_DIR = paths.sessions_dir()

_SECONDS_PER_DAY = 86_400
_BYTES_PER_MB = 1024 * 1024

_locks: dict[str, asyncio.Lock] = {}

# Wall-clock of the last maintenance scan, for the save()-triggered time gate.
# Module-level so the gate survives across calls; reset by tests for determinism.
_last_cleanup_at: float | None = None

# Handle for the process-internal periodic maintenance task (server lifespan only).
# Module-level + resettable in tests, mirroring mcp_client._health_monitor_task.
_maintenance_task: asyncio.Task[None] | None = None


def _default_config() -> dict[str, float]:
    from fleetent import agent_config

    s = agent_config.active_agent_or_default()
    return {
        "ttl_seconds": s.session_ttl_days * _SECONDS_PER_DAY,
        "max_total_bytes": s.session_max_total_mb * _BYTES_PER_MB,
        "max_count": s.session_max_count,
        "cleanup_interval_seconds": s.session_cleanup_interval_seconds,
    }


def maybe_run_maintenance(*, _now: float | None = None) -> list[str]:
    """Run TTL cleanup + capacity enforcement at most once per interval (internal trigger).

    Called opportunistically from save() so expired sessions are pruned and disk
    capacity is bounded as a side effect of normal session activity — no external
    scheduler/cron is required. Both passes (TTL first, then capacity) are time-gated
    together to run at most once per `session_cleanup_interval_seconds`, so the common
    save path stays cheap.

    Returns the session_ids removed this run (expired + capacity-evicted), or [] when
    the gate is closed.
    """
    global _last_cleanup_at
    now = time.time() if _now is None else _now
    interval = _default_config()["cleanup_interval_seconds"]
    if _last_cleanup_at is not None and now - _last_cleanup_at < interval:
        return []
    _last_cleanup_at = now
    removed = cleanup_expired(_now=now)
    removed += enforce_capacity()
    return removed


async def _session_maintenance_loop(interval: float) -> None:
    """Periodically trigger session cleanup (bare asyncio, no cron_scheduler).

    Reuses maybe_run_maintenance() so TTL/capacity/SB2-release semantics stay in one
    place. Each iteration is fault-isolated: a single cleanup failure is logged and the
    loop continues — one failure MUST NOT kill the resident task and silently lose all
    subsequent periodic cleanups.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            removed = maybe_run_maintenance()
            # Release removed sessions' sandbox containers too, mirroring save(). The
            # loop is exactly the silent-period case where save() is NOT running, so
            # without this, periodically-cleaned sessions would leak their containers.
            await _release_sandboxes(removed)
        except Exception as exc:  # noqa: BLE001 — a single failure must not kill the loop
            _logger.warn("session_maintenance_loop_iteration_failed", error=str(exc))


def start_session_maintenance(*, interval: float | None = None) -> asyncio.Task[None]:
    """Start the background session-maintenance task (server lifespan only, not CLI).

    Implemented as a bare ``asyncio.create_task`` loop — deliberately NOT routed through
    cron_scheduler/APScheduler (decoupled from the deferred user-level scheduler, per the
    MCP3 health-monitor precedent and lead direction). Idempotent: a running task is
    returned as-is rather than replaced.
    """
    global _maintenance_task
    if _maintenance_task is not None and not _maintenance_task.done():
        return _maintenance_task
    if interval is None:
        from fleetent import agent_config

        interval = agent_config.active_agent_or_default().session_cleanup_interval_seconds
    _maintenance_task = asyncio.create_task(_session_maintenance_loop(interval))
    return _maintenance_task


async def stop_session_maintenance() -> None:
    """Cancel the background session-maintenance task, leaving no residual task."""
    global _maintenance_task
    if _maintenance_task is None:
        return
    _maintenance_task.cancel()
    with suppress(asyncio.CancelledError):
        await _maintenance_task
    _maintenance_task = None


def is_expired(mtime: float, now: float, ttl_seconds: float) -> bool:
    """Return True when the session's last-active time is older than the TTL.

    The boundary (`now - mtime` exactly equal to `ttl_seconds`) is NOT expired.
    """
    return now - mtime > ttl_seconds


def cleanup_expired(
    ttl_seconds: float | None = None,
    *,
    _now: float | None = None,
) -> list[str]:
    """Delete session files whose last-active time (mtime) exceeds the TTL.

    Scans `SESSIONS_DIR` recursively so session_ids containing `/` (stored in
    subdirectories) are handled; `.json.tmp` atomic-write temporaries are skipped.
    A single file's deletion failure is logged and does not abort the batch.

    Args:
        ttl_seconds: TTL in seconds; falls back to `_default_config()` when None.
        _now: Override for the current time (testing); defaults to `time.time()`.

    Returns:
        The session_ids of the files that were successfully deleted.
    """
    if ttl_seconds is None:
        ttl_seconds = _default_config()["ttl_seconds"]
    now = time.time() if _now is None else _now

    if not SESSIONS_DIR.exists():
        return []

    removed: list[str] = []
    for path in SESSIONS_DIR.rglob("*.json"):
        if path.name.endswith(".json.tmp"):
            continue
        if path.name.endswith(".pre-compact.json"):
            continue  # backup files follow the main file, not independent TTL
        if ".tool_outputs/" in path.relative_to(SESSIONS_DIR).as_posix():
            continue  # externalized tool result files are not sessions
        if not is_expired(path.stat().st_mtime, now, ttl_seconds):
            continue
        session_id = path.relative_to(SESSIONS_DIR).with_suffix("").as_posix()
        try:
            path.unlink()
        except OSError as exc:
            _logger.warn("session_cleanup_delete_failed", session_id=session_id, error=str(exc))
            continue
        removed.append(session_id)
        _logger.info("session_cleanup_deleted", session_id=session_id)
        # Best-effort: remove the pre-compaction backup alongside the main file
        with suppress(OSError):
            (SESSIONS_DIR / f"{session_id}.pre-compact.json").unlink()
        # Best-effort: remove the externalized tool-result directory
        shutil.rmtree(SESSIONS_DIR / f"{session_id}.tool_outputs", ignore_errors=True)
        # Best-effort: remove the agent-side resume marker
        with suppress(OSError):
            (SESSIONS_DIR / f"{session_id}.resume").unlink()
        # Best-effort: remove the agent-side todo list
        with suppress(OSError):
            (SESSIONS_DIR / f"{session_id}.todo").unlink()
        # Best-effort: remove the flock anchor file. Safe here (not at unlock time,
        # where deletion races with concurrent lockers): the session is expired, and
        # flock binds to the inode — a hypothetical live holder is unaffected.
        with suppress(OSError):
            (SESSIONS_DIR / f"{session_id}.lock").unlink()

    _logger.info("session_cleanup_done", removed_count=len(removed), ttl_seconds=ttl_seconds)
    if removed:
        from fleetent.session import index as session_index

        try:
            session_index.delete_batch(removed)
        except Exception as exc:  # noqa: BLE001 — index sync must not break file cleanup
            _logger.warn("session_cleanup_index_sync_failed", count=len(removed), error=str(exc))
    return removed


def is_over_capacity(
    total_bytes: float,
    count: float,
    max_total_bytes: float,
    max_count: float,
) -> bool:
    """Return True when an enabled capacity dimension exceeds its limit.

    A limit of 0 (or any non-positive value) disables that dimension: it is
    neither used to detect over-capacity nor as a stop condition. When both
    dimensions are disabled the system is never over capacity.
    """
    if max_total_bytes > 0 and total_bytes > max_total_bytes:
        return True
    return max_count > 0 and count > max_count


def _scan_sessions() -> list[tuple[str, int, float]]:
    """Collect `(session_id, size, mtime)` for every persisted session file.

    Recurses `SESSIONS_DIR` so session_ids containing `/` (stored in
    subdirectories) are restored; `.json.tmp` atomic-write temporaries are
    excluded so they are neither counted nor evicted.
    """
    if not SESSIONS_DIR.exists():
        return []

    entries: list[tuple[str, int, float]] = []
    for path in SESSIONS_DIR.rglob("*.json"):
        if path.name.endswith(".json.tmp"):
            continue
        stat = path.stat()
        session_id = path.relative_to(SESSIONS_DIR).with_suffix("").as_posix()
        entries.append((session_id, stat.st_size, stat.st_mtime))
    return entries


def enforce_capacity(
    max_total_bytes: float | None = None,
    max_count: float | None = None,
) -> list[str]:
    """Evict oldest sessions (LRU by mtime) until both capacity limits hold.

    Two independent limits: total session-file bytes and total session count.
    Either exceeding its limit triggers eviction; sessions are deleted in
    ascending mtime order (least-recently-active first) until both *enabled*
    limits are satisfied. A limit of 0 (or None falling back to a 0 default)
    disables that dimension. When both are disabled nothing is evicted.

    Deletion is fault-tolerant: a single file's failure is logged and skipped
    without aborting the batch, and the running accumulators are decremented
    per eviction attempt so a stuck file does not cascade into over-eviction
    of healthy sessions. `.json.tmp` temporaries are never touched.

    Args:
        max_total_bytes: Total-size limit in bytes; falls back to
            `_default_config()` when None. Non-positive disables the dimension.
        max_count: Max session count; falls back to `_default_config()` when
            None. Non-positive disables the dimension.

    Returns:
        The session_ids of the files that were successfully deleted, in
        eviction (oldest-first) order.
    """
    if max_total_bytes is None:
        max_total_bytes = _default_config()["max_total_bytes"]
    if max_count is None:
        max_count = _default_config()["max_count"]

    entries = _scan_sessions()
    total_bytes = float(sum(size for _, size, _ in entries))
    count = float(len(entries))

    if not is_over_capacity(total_bytes, count, max_total_bytes, max_count):
        return []

    reasons: list[str] = []
    if max_total_bytes > 0 and total_bytes > max_total_bytes:
        reasons.append("total_bytes")
    if max_count > 0 and count > max_count:
        reasons.append("count")

    removed: list[str] = []
    for session_id, size, _ in sorted(entries, key=lambda e: e[2]):
        if not is_over_capacity(total_bytes, count, max_total_bytes, max_count):
            break
        # Decrement on attempt so a failed deletion cannot cascade-evict healthy
        # sessions; the stuck file is simply skipped and retried on the next run.
        total_bytes -= size
        count -= 1
        path = SESSIONS_DIR / f"{session_id}.json"
        try:
            path.unlink()
        except OSError as exc:
            _logger.warn("session_capacity_delete_failed", session_id=session_id, error=str(exc))
            continue
        removed.append(session_id)
        _logger.info("session_capacity_evicted", session_id=session_id)

    _logger.info(
        "session_capacity_done",
        evicted_count=len(removed),
        reasons=reasons,
        max_total_bytes=max_total_bytes,
        max_count=max_count,
    )
    if removed:
        from fleetent.session import index as session_index

        try:
            session_index.delete_batch(removed)
        except Exception as exc:  # noqa: BLE001 — index sync must not break capacity eviction
            _logger.warn("session_capacity_index_sync_failed", count=len(removed), error=str(exc))
    return removed


def list_by_user(
    user_id: str,
    limit: int = 50,
    before_updated_at: float | None = None,
) -> list[dict[str, object]]:
    """Return sessions for a user, most-recently-active first, with cursor pagination."""
    from fleetent.session import index as session_index

    return session_index.list_by_user(user_id, limit=limit, before_updated_at=before_updated_at)


def write_compaction_checkpoint(session_id: str, messages: list[dict[str, object]]) -> None:
    """Atomically write the pre-compaction message snapshot for a session.

    Overwrites any previous checkpoint so only the most recent pre-compact state
    is kept. Caller is responsible for best-effort error handling.
    """
    path = SESSIONS_DIR / f"{session_id}.pre-compact.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".pre-compact.json.tmp")
    tmp.write_text(
        json.dumps({"messages": messages, "compacted_at": time.time()}, ensure_ascii=False)
    )
    tmp.replace(path)


def delete_compaction_checkpoint(session_id: str) -> None:
    """Remove the pre-compaction backup file if it exists. Idempotent."""
    path = SESSIONS_DIR / f"{session_id}.pre-compact.json"
    with suppress(FileNotFoundError):
        path.unlink()


def _resume_marker_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.resume"


def mark_resume_pending(session_id: str) -> None:
    """Mark a session as resume-pending via an agent-side .resume marker file.

    Pure agent-side state (no DB, no platform): the marker's existence is the flag.
    """
    path = _resume_marker_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def is_resume_pending(session_id: str) -> bool:
    """True when the session's .resume marker exists."""
    return _resume_marker_path(session_id).exists()


def clear_resume_pending(session_id: str) -> None:
    """Remove the .resume marker. Idempotent."""
    with suppress(FileNotFoundError):
        _resume_marker_path(session_id).unlink()


def scan_and_mark_recent_resume(window_seconds: int = 120) -> list[str]:
    """Mark sessions whose file mtime is within the last window_seconds as resume-pending.

    Agent-side restart recovery: based purely on session file mtime, no platform/DB.
    Returns the session_ids that were marked.
    """
    now = time.time()
    marked: list[str] = []
    for session_id, _size, mtime in _scan_sessions():
        if now - mtime <= window_seconds:
            mark_resume_pending(session_id)
            marked.append(session_id)
    return marked


def _todo_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.todo"


def read_todo(session_id: str) -> list[dict[str, str]]:
    """Read the agent-side persisted todo list for a session.

    Returns [] when the file is absent or its content is unreadable — todo is a
    best-effort task list and MUST NOT break a run on corruption.
    """
    path = _todo_path(session_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        _logger.warn("session_todo_read_failed", session_id=session_id, error=str(exc))
        return []
    return list(data) if isinstance(data, list) else []


def write_todo(session_id: str, items: list[dict[str, str]]) -> None:
    """Persist the todo list to the agent-side ``{session_id}.todo`` sibling file.

    Atomic (tmp→replace). Deliberately does NOT acquire ``session_lock``: the todo
    tool runs inside the agent loop, and on the IM path the loop already holds the
    session lock for the whole run — re-acquiring it here would deadlock (mirrors
    ``write_compaction_checkpoint`` / ``mark_resume_pending``).
    """
    path = _todo_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.tmp"
    tmp.write_text(json.dumps(items, ensure_ascii=False))
    tmp.replace(path)


def clear_todo(session_id: str) -> None:
    """Remove the ``{session_id}.todo`` file if it exists. Idempotent."""
    with suppress(FileNotFoundError):
        _todo_path(session_id).unlink()


def externalize_tool_results(
    session_id: str, messages: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Move oversized tool results to per-session external files, leaving references.

    Returns a new list; the input is never mutated. Only ``role == "tool"`` messages
    whose string content exceeds the inline limit and that carry a ``tool_call_id``
    are externalized to ``{session_id}.tool_outputs/{tool_call_id}.txt``.
    """
    out_dir = SESSIONS_DIR / f"{session_id}.tool_outputs"
    result: list[dict[str, object]] = []
    for msg in messages:
        content = msg.get("content")
        call_id = msg.get("tool_call_id")
        if (
            msg.get("role") == "tool"
            and isinstance(content, str)
            and isinstance(call_id, str)
            and len(content) > _TOOL_RESULT_INLINE_LIMIT
        ):
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{call_id}.txt"
            tmp = path.with_suffix(".txt.tmp")
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(path)
            result.append({**msg, "content": f"{_STORED_PREFIX}{call_id}{_STORED_SUFFIX}"})
        else:
            result.append(msg)
    return result


def rehydrate_tool_results(
    session_id: str, messages: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Inverse of externalize_tool_results: read external content back inline.

    Returns a new list; the input is never mutated. A missing external file leaves
    the ``[stored:...]`` reference in place rather than failing.
    """
    out_dir = SESSIONS_DIR / f"{session_id}.tool_outputs"
    result: list[dict[str, object]] = []
    for msg in messages:
        content = msg.get("content")
        if (
            isinstance(content, str)
            and content.startswith(_STORED_PREFIX)
            and content.endswith(_STORED_SUFFIX)
        ):
            call_id = content[len(_STORED_PREFIX) : -len(_STORED_SUFFIX)]
            path = out_dir / f"{call_id}.txt"
            if path.exists():
                result.append({**msg, "content": path.read_text(encoding="utf-8")})
            else:
                result.append(msg)  # external file gone — keep the placeholder
        else:
            result.append(msg)
    return result


def _get_lock(session_id: str) -> asyncio.Lock:
    if session_id not in _locks:
        _locks[session_id] = asyncio.Lock()
    return _locks[session_id]


@asynccontextmanager
async def session_lock(session_id: str) -> AsyncIterator[None]:
    """Serialize same-session writes within and across processes.

    Two-layer lock: a cross-process file lock (fcntl.flock on {session_id}.lock)
    wraps the per-session in-process asyncio.Lock. On non-POSIX platforms the file
    lock is unavailable and only the asyncio.Lock applies.
    """
    if not _flock_available:
        async with _get_lock(session_id):
            yield
        return

    lock_path = SESSIONS_DIR / f"{session_id}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("w")
    try:
        # flock is blocking — offload to a thread so the event loop keeps running.
        await asyncio.to_thread(fcntl.flock, handle.fileno(), fcntl.LOCK_EX)
        async with _get_lock(session_id):
            yield
    finally:
        with suppress(Exception):
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _read(session_id: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Return (messages, meta), tolerating both the legacy list format and the
    current ``{"meta": ..., "messages": ...}`` envelope."""
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return [], {}
    raw = json.loads(path.read_text())
    if isinstance(raw, list):  # legacy: bare top-level message list
        return list(raw), {}
    return list(raw.get("messages", [])), dict(raw.get("meta", {}))


def list_session_ids(prefix: str = "", limit: int | None = None) -> list[str]:
    """Return persisted session ids, optionally filtered to those under ``prefix``.

    Additive read helper (tui-gateway): lets the TUI gateway enumerate a user's
    sessions without changing any existing session contract. Ids are derived the
    same way as the maintenance scanners (recurses subdirs, skips ``.json.tmp``).
    """
    result = sorted(sid for sid, _size, _mtime in _scan_sessions() if sid.startswith(prefix))
    return result[:limit] if limit is not None else result


async def load(session_id: str) -> list[dict[str, object]]:
    messages, _ = _read(session_id)
    return rehydrate_tool_results(session_id, messages)


async def load_meta(session_id: str) -> dict[str, object]:
    _, meta = _read(session_id)
    return meta


_PENDING_APPROVALS_KEY = "pending_approvals"


def _write_envelope(
    session_id: str, messages: list[dict[str, object]], meta: dict[str, object]
) -> None:
    """Atomically persist a {meta, messages} envelope as-is (no re-externalization).

    For meta-only mutations the stored message list is written back verbatim so the
    bookkeeping never round-trips messages through rehydrate/externalize.
    """
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSIONS_DIR / f"{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"meta": meta, "messages": messages}, ensure_ascii=False))
    tmp.replace(path)


async def add_pending_approval(session_id: str, approval_id: str, entry: dict[str, object]) -> None:
    """Record a suspended tool call awaiting approval under ``meta.pending_approvals``.

    The caller MUST already hold this session's lock — the loop persists pending from
    inside the normalizer's ``session_lock``; resume and reconcile likewise hold it.
    This helper does NOT re-acquire it: ``session_lock`` is non-reentrant, so a second
    acquire from the same task would deadlock the run (which kept ``is_running`` True
    and made steering swallow every later same-session message).
    """
    messages, meta = _read(session_id)
    pending = dict(meta.get(_PENDING_APPROVALS_KEY) or {})
    pending[approval_id] = entry
    meta[_PENDING_APPROVALS_KEY] = pending
    _write_envelope(session_id, messages, meta)


async def get_pending_approval(session_id: str, approval_id: str) -> dict[str, object] | None:
    """Return one pending-approval entry, or None if absent."""
    _, meta = _read(session_id)
    pending = meta.get(_PENDING_APPROVALS_KEY) or {}
    entry = pending.get(approval_id)
    return dict(entry) if isinstance(entry, dict) else None


async def list_pending_approvals(session_id: str) -> dict[str, dict[str, object]]:
    """Return all pending-approval entries keyed by approval_id (empty when none)."""
    _, meta = _read(session_id)
    pending = meta.get(_PENDING_APPROVALS_KEY) or {}
    return {k: dict(v) for k, v in pending.items() if isinstance(v, dict)}


async def remove_pending_approval(session_id: str, approval_id: str) -> None:
    """Drop a resolved/expired pending-approval entry (no-op if absent).

    Caller MUST hold this session's lock (see ``add_pending_approval``); this helper
    does not re-acquire the non-reentrant lock.
    """
    messages, meta = _read(session_id)
    pending = dict(meta.get(_PENDING_APPROVALS_KEY) or {})
    if approval_id in pending:
        del pending[approval_id]
        meta[_PENDING_APPROVALS_KEY] = pending
        _write_envelope(session_id, messages, meta)


async def save(
    session_id: str,
    messages: list[dict[str, object]],
    meta: dict[str, object] | None = None,
    user_id: str | None = None,
) -> None:
    # main's meta envelope + zhangyang's session_index update, merged: omitting
    # meta preserves any meta already persisted (e.g. a pinned agent version)
    # while user_id still feeds the activity index below.
    if meta is None:
        _, meta = _read(session_id)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSIONS_DIR / f"{session_id}.json"
    # Create the target's parent (not just SESSIONS_DIR): session_ids may contain
    # "/" (e.g. IM platform/channel/user), nesting the file in subdirectories.
    path.parent.mkdir(parents=True, exist_ok=True)
    # Externalize oversized tool results before serialization; persists references
    # in the JSON while the full content lives in the .tool_outputs sibling dir.
    externalized = externalize_tool_results(session_id, messages)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"meta": meta, "messages": externalized}, ensure_ascii=False))
    tmp.replace(path)

    # Best-effort metadata index update: the message file is the source of truth
    # and is already durably written, so an index failure is logged and swallowed
    # rather than rolling back the successful save.
    from fleetent.session import index as session_index

    try:
        session_index.record_activity(
            session_id,
            user_id=user_id,
            message_count=len(messages),
        )
    except Exception as exc:  # noqa: BLE001 — auxiliary index must not break persistence
        _logger.warn("session_index_update_failed", session_id=session_id, error=str(exc))

    # Internal maintenance trigger (no external cron): opportunistically prune
    # expired sessions and enforce disk capacity as a side effect of activity,
    # time-gated to stay cheap. Fault-isolated — maintenance must never break the
    # just-completed persistence.
    try:
        removed = maybe_run_maintenance()
        await _release_sandboxes(removed)
    except Exception as exc:  # noqa: BLE001 — maintenance must not break persistence
        _logger.warn("session_maintenance_trigger_failed", session_id=session_id, error=str(exc))


async def clear(session_id: str) -> None:
    """Empty a session's transcript (admin clear / IM `/new`), under the session lock."""
    async with session_lock(session_id):
        await save(session_id, [])


async def reset(session_id: str, keep_turns: int) -> None:
    """Truncate a transcript to its first ``keep_turns`` messages, under the lock."""
    async with session_lock(session_id):
        messages = await load(session_id)
        await save(session_id, messages[:keep_turns])


async def inject_message(session_id: str, role: str, content: str) -> None:
    """Append a single message to a session's transcript atomically under the lock.

    Used by the admin console (chat_admin_api) to inject a human-agent reply during a
    takeover. Grafted from main's session_mgr during the architecture merge.
    """
    async with session_lock(session_id):
        messages = await load(session_id)
        messages.append({"role": role, "content": content})
        await save(session_id, messages)


async def _release_sandboxes(session_ids: list[str]) -> None:
    """Reclaim session-scope sandbox containers for maintenance-removed sessions.

    Lazy-imports the sandbox manager (tools depends on session_mgr indirectly, so a
    top-level import would close an import cycle). Best-effort: a release failure is
    logged and swallowed, never propagated into the save path that already persisted.
    release_session is a no-op for sessions without a session-scope container.
    """
    if not session_ids:
        return
    from fleetent.tools.builtin_tools import _get_manager

    manager = _get_manager()
    # Per-id isolation: one stuck container must not block reclaiming the others.
    for session_id in session_ids:
        try:
            await manager.release_session(session_id)
        except Exception as exc:  # noqa: BLE001 — sandbox reclaim must not break persistence
            _logger.warn("sandbox_release_failed", session_id=session_id, error=str(exc))
