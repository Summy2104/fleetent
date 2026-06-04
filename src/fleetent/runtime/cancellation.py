"""Cancellation propagation primitive (AR19).

A `CancelToken` is a one-way cancellation signal passed explicitly from the agent
loop into tool execution. It carries an explicit cancel flag plus an optional
absolute `deadline` on the monotonic clock; `is_cancelled()` merges both into a
single query so consumers never have to check two things. `CancellationChecker`
plugs the token into the AR1 termination framework so the loop stops with
`StopReason.cancelled` at its next checkpoint.

This module defines the contract wave-3 timeout features (T2 / SB7) reuse: a
timeout is just `CancelToken(deadline=now + timeout)`. No global mutable state —
the token is a per-run object threaded explicitly through callers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from fleetent.runtime.termination import LoopState, StopReason

# Marks a tool parameter as runtime out-of-band injection: `dispatch` supplies it
# and `_build_schema` excludes it from the LLM-facing schema. The conventional
# parameter name a tool declares to opt into receiving the token.
CANCEL_TOKEN_PARAM = "cancel_token"


@dataclass
class CancelToken:
    """One-way cooperative cancellation signal with an optional hard deadline.

    Args:
        deadline: Absolute `time.monotonic()` value past which the token is
            considered cancelled. None means no deadline (cancellation only via
            an explicit `cancel()` call). The default token never cancels.
        parent: Optional upstream token (AR20 incremental add). When set,
            `is_cancelled()` also reflects the parent's cancellation, letting a
            child token merge "own deadline" with "external/parent cancel"
            without a watchdog. Default None preserves prior single-source
            semantics for every existing caller.
    """

    deadline: float | None = None
    parent: CancelToken | None = None
    _cancelled: bool = False

    def cancel(self) -> None:
        """Mark the token cancelled. Idempotent."""
        self._cancelled = True

    def is_cancelled(self) -> bool:
        """True once explicitly cancelled, the deadline passed, or the parent is."""
        if self._cancelled:
            return True
        if self.deadline is not None and time.monotonic() >= self.deadline:
            return True
        return self.parent is not None and self.parent.is_cancelled()


class CancellationChecker:
    """Termination checker that stops the loop when its token is cancelled."""

    def __init__(self, token: CancelToken) -> None:
        self._token = token

    def check(self, state: LoopState) -> StopReason | None:
        return StopReason.cancelled if self._token.is_cancelled() else None
