from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

SESSIONS_DIR = Path("data/sessions")

_locks: dict[str, asyncio.Lock] = {}


def _get_lock(session_id: str) -> asyncio.Lock:
    if session_id not in _locks:
        _locks[session_id] = asyncio.Lock()
    return _locks[session_id]


@asynccontextmanager
async def session_lock(session_id: str) -> AsyncIterator[None]:
    async with _get_lock(session_id):
        yield


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


async def load(session_id: str) -> list[dict[str, object]]:
    messages, _ = _read(session_id)
    return messages


async def load_meta(session_id: str) -> dict[str, object]:
    _, meta = _read(session_id)
    return meta


async def save(
    session_id: str,
    messages: list[dict[str, object]],
    meta: dict[str, object] | None = None,
) -> None:
    # Omitting meta must preserve any meta already persisted (e.g. appending a
    # turn should not drop the session's pinned agent version).
    if meta is None:
        _, meta = _read(session_id)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSIONS_DIR / f"{session_id}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"meta": meta, "messages": messages}, ensure_ascii=False))
    tmp.replace(path)


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

    Used by the admin console to inject a human-agent reply during a takeover.
    """
    async with session_lock(session_id):
        messages = await load(session_id)
        messages.append({"role": role, "content": content})
        await save(session_id, messages)
