"""Run-time input steering (C1): inject/interrupt input into an in-flight run.

An input source (the IM gateway) registers an active run per session; while it is
in flight, a newly arrived message can be *steered* into it (queued for injection
at the next turn boundary) or *interrupt* it, instead of blocking on the session
lock and silently serializing into a brand-new turn.

The agent loop is a passive consumer: it only ``drain``s the per-session mailbox at
each turn boundary, so it stays unaware of who (if anyone) is steering — when no run
is registered for a session, every loop-side call is a no-op.

Pure agent-side, asyncio-only. The module-level registry is reset/injectable for
tests (``reset``); keys are per-session so runs never cross-talk.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fleetent.structured_logging import get_logger
from fleetent.runtime.cancellation import CancelToken

_logger = get_logger("runtime.steering")

_DEFAULT_MAX_PENDING = 8


@dataclass
class RunHandle:
    """Per-session active-run state: its cancel token + pending-injection mailbox."""

    token: CancelToken
    pending: asyncio.Queue[str]


# session_id -> RunHandle. Module-level so the IM gateway and the loop share it;
# reset()-able and monkeypatch-injectable for tests (no cross-test leakage).
_active: dict[str, RunHandle] = {}


def reset() -> None:
    """Test hook: drop all active-run registrations."""
    _active.clear()


def is_running(session_id: str) -> bool:
    """Whether a run is currently registered (in flight) for this session."""
    return session_id in _active


@asynccontextmanager
async def register_run(
    session_id: str,
    token: CancelToken,
    *,
    max_pending: int = _DEFAULT_MAX_PENDING,
) -> AsyncIterator[RunHandle]:
    """Register an active run for ``session_id`` for the duration of the block.

    The ``finally`` guarantees the handle is removed even on error, so a stale
    registration can never leak (which would make a finished session look "running"
    forever). Identity check on removal so a re-registration is not clobbered.
    """
    handle = RunHandle(token=token, pending=asyncio.Queue(maxsize=max(1, max_pending)))
    _active[session_id] = handle
    try:
        yield handle
    finally:
        if _active.get(session_id) is handle:
            del _active[session_id]


def steer(session_id: str, text: str) -> bool:
    """Queue ``text`` for injection into the running session's next turn.

    Returns False when no run is active (caller should start a normal new turn) or
    the mailbox is full (back-pressure: drop and let the caller tell the user to
    retry), so a steered message is never silently lost without a False signal.
    """
    handle = _active.get(session_id)
    if handle is None:
        return False
    try:
        handle.pending.put_nowait(text)
    except asyncio.QueueFull:
        _logger.warn("steering_mailbox_full", session_id=session_id)
        return False
    return True


def interrupt(session_id: str) -> bool:
    """Cancel the active run for a session via its token; False if none active."""
    handle = _active.get(session_id)
    if handle is None:
        return False
    handle.token.cancel()
    return True


def drain(session_id: str) -> list[str]:
    """Pop and return all pending steered messages for a session (loop-side)."""
    handle = _active.get(session_id)
    if handle is None:
        return []
    out: list[str] = []
    while True:
        try:
            out.append(handle.pending.get_nowait())
        except asyncio.QueueEmpty:
            break
    return out
