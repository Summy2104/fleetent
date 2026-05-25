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
