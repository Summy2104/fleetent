"""Session-scoped user input gate for the clarify tool.

Semantically distinct from permission_gate (which is for risk approval):
this gate suspends the agent loop waiting for a user-supplied answer,
not a security decision. Each session gets its own asyncio.Event.

Module-level answer()/wait_for_answer() convenience functions operate on
the shared _DEFAULT_GATE singleton, which is what the clarify tool uses.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_TIMEOUT_MSG = "timeout: 用户未在规定时间内回答"


@dataclass
class _Entry:
    event: asyncio.Event = field(default_factory=asyncio.Event)
    answer: str | None = None


class UserInputGate:
    """Manages per-session answer events."""

    def __init__(self) -> None:
        self._sessions: dict[str, _Entry] = {}

    def _get_or_create(self, session_id: str) -> _Entry:
        if session_id not in self._sessions:
            self._sessions[session_id] = _Entry()
        return self._sessions[session_id]

    def answer(self, session_id: str, text: str) -> None:
        """Record the user's answer and unblock any waiting coroutine."""
        entry = self._get_or_create(session_id)
        entry.answer = text
        entry.event.set()

    async def wait(self, session_id: str, timeout: float = 300.0) -> str:
        """Block until answer() is called for this session or timeout fires."""
        entry = self._get_or_create(session_id)
        try:
            await asyncio.wait_for(entry.event.wait(), timeout=timeout)
        except TimeoutError:
            return f"{_TIMEOUT_MSG}（{timeout:.0f}s）"
        finally:
            # Always clean up after wait resolves to prevent memory leaks
            self._sessions.pop(session_id, None)
        return entry.answer or ""

    def cleanup(self, session_id: str) -> None:
        """Remove session entry explicitly (e.g. on session teardown)."""
        self._sessions.pop(session_id, None)


# Module-level singleton used by the clarify tool and IM gateway callbacks.
_DEFAULT_GATE = UserInputGate()


def answer(session_id: str, text: str) -> None:
    """Record a user answer on the shared gate."""
    _DEFAULT_GATE.answer(session_id, text)


async def wait_for_answer(session_id: str, timeout: float = 300.0) -> str:
    """Wait for a user answer on the shared gate."""
    return await _DEFAULT_GATE.wait(session_id, timeout=timeout)
