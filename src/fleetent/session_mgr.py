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

_locks: dict[str, asyncio.Lock] = {}


def _default_config() -> dict[str, float]:
    from fleetent.config import Settings

    s = Settings()
    return {"ttl_seconds": s.session_ttl_days * _SECONDS_PER_DAY}


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


async def save(session_id: str, messages: list[dict[str, object]]) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSIONS_DIR / f"{session_id}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(messages, ensure_ascii=False))
    tmp.replace(path)
