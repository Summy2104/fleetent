from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

SESSIONS_DIR = Path("data/sessions")

_SECONDS_PER_DAY = 86_400
_BYTES_PER_MB = 1024 * 1024

_locks: dict[str, asyncio.Lock] = {}

# Wall-clock of the last maintenance scan, for the save()-triggered time gate.
# Module-level so the gate survives across calls; reset by tests for determinism.
_last_cleanup_at: float | None = None


def _default_config() -> dict[str, float]:
    from fleetent.config import Settings

    s = Settings()
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
        if not is_expired(path.stat().st_mtime, now, ttl_seconds):
            continue
        session_id = path.relative_to(SESSIONS_DIR).with_suffix("").as_posix()
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("session_cleanup_delete_failed", session_id=session_id, error=str(exc))
            continue
        removed.append(session_id)
        logger.info("session_cleanup_deleted", session_id=session_id)

    logger.info("session_cleanup_done", removed_count=len(removed), ttl_seconds=ttl_seconds)
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
            logger.warning("session_capacity_delete_failed", session_id=session_id, error=str(exc))
            continue
        removed.append(session_id)
        logger.info("session_capacity_evicted", session_id=session_id)

    logger.info(
        "session_capacity_done",
        evicted_count=len(removed),
        reasons=reasons,
        max_total_bytes=max_total_bytes,
        max_count=max_count,
    )
    return removed


def _get_lock(session_id: str) -> asyncio.Lock:
    if session_id not in _locks:
        _locks[session_id] = asyncio.Lock()
    return _locks[session_id]


@asynccontextmanager
async def session_lock(session_id: str) -> AsyncIterator[None]:
    async with _get_lock(session_id):
        yield


async def load(session_id: str) -> list[dict[str, object]]:
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return []
    return list(json.loads(path.read_text()))


async def save(
    session_id: str,
    messages: list[dict[str, object]],
    user_id: str | None = None,
    agent_name: str | None = None,
) -> None:
    path = SESSIONS_DIR / f"{session_id}.json"
    # Create the target's parent (not just SESSIONS_DIR): session_ids may contain
    # "/" (e.g. IM platform/channel/user), nesting the file in subdirectories.
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(messages, ensure_ascii=False))
    tmp.replace(path)

    # Best-effort metadata index update: the message file is the source of truth
    # and is already durably written, so an index failure is logged and swallowed
    # rather than rolling back the successful save.
    from fleetent import session_index

    try:
        session_index.record_activity(
            session_id,
            user_id=user_id,
            message_count=len(messages),
            agent_name=agent_name,
        )
    except Exception as exc:  # noqa: BLE001 — auxiliary index must not break persistence
        logger.warning("session_index_update_failed", session_id=session_id, error=str(exc))

    # Internal maintenance trigger (no external cron): opportunistically prune
    # expired sessions and enforce disk capacity as a side effect of activity,
    # time-gated to stay cheap. Fault-isolated — maintenance must never break the
    # just-completed persistence.
    try:
        removed = maybe_run_maintenance()
        await _release_sandboxes(removed)
    except Exception as exc:  # noqa: BLE001 — maintenance must not break persistence
        logger.warning("session_maintenance_trigger_failed", session_id=session_id, error=str(exc))


async def _release_sandboxes(session_ids: list[str]) -> None:
    """Reclaim session-scope sandbox containers for maintenance-removed sessions.

    Lazy-imports the sandbox manager (tools depends on session_mgr indirectly, so a
    top-level import would close an import cycle). Best-effort: a release failure is
    logged and swallowed, never propagated into the save path that already persisted.
    release_session is a no-op for sessions without a session-scope container.
    """
    if not session_ids:
        return
    from fleetent.tools import _get_manager

    manager = _get_manager()
    # Per-id isolation: one stuck container must not block reclaiming the others.
    for session_id in session_ids:
        try:
            await manager.release_session(session_id)
        except Exception as exc:  # noqa: BLE001 — sandbox reclaim must not break persistence
            logger.warning("sandbox_release_failed", session_id=session_id, error=str(exc))
