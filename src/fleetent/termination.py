"""Agent-loop termination framework.

Provides a single, extensible checkpoint for deciding when (and why) the agent
loop must stop. Each termination reason is an independent checker registered on
a `TerminationController`; new reasons (loop detection, budget, cancellation)
plug in by registering a checker rather than editing the loop body.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

LimitConfig = dict[str, int]


def _default_config() -> LimitConfig:
    """Deployment-level defaults from Settings (env-configurable). Lazy import
    mirrors context_mgr._default_config to keep this module import-light."""
    from fleetent.config import Settings

    s = Settings()
    return {
        "max_turns": s.agent_max_turns,
        "max_consecutive_failures": s.agent_max_consecutive_failures,
    }


def resolve_limits(
    max_turns: int | None = None,
    max_consecutive_failures: int | None = None,
    config: LimitConfig | None = None,
) -> tuple[int, int]:
    """Resolve effective limits. Precedence: call param > config/Settings > default."""
    cfg = config if config is not None else _default_config()
    return (
        max_turns if max_turns is not None else cfg["max_turns"],
        (
            max_consecutive_failures
            if max_consecutive_failures is not None
            else cfg["max_consecutive_failures"]
        ),
    )


class StopReason(StrEnum):
    """Why the agent loop stopped. str-valued for clean JSONL trace serialization."""

    normal = "normal"
    max_turns = "max_turns"
    consecutive_failures = "consecutive_failures"
    approval_rejected = "approval_rejected"
    # Reserved: defined here so trace consumers know the full vocabulary, but no
    # checker is registered for these in this change (see proposal/design).
    loop_detected = "loop_detected"
    budget_exceeded = "budget_exceeded"
    cancelled = "cancelled"


@dataclass
class LoopState:
    """Mutable per-run state the loop updates and termination checkers read."""

    turn: int = 0
    consecutive_failures: int = 0
    approval_rejected: bool = False


class TerminationChecker(Protocol):
    """A single termination strategy. Returns a StopReason to stop, else None."""

    def check(self, state: LoopState) -> StopReason | None: ...


class TerminationController:
    """Holds an ordered list of checkers and evaluates them at each checkpoint."""

    def __init__(self) -> None:
        self._checkers: list[TerminationChecker] = []

    def register(self, checker: TerminationChecker) -> None:
        self._checkers.append(checker)

    def should_stop(self, state: LoopState) -> StopReason | None:
        """Return the first non-None reason; None if no checker wants to stop."""
        for checker in self._checkers:
            reason = checker.check(state)
            if reason is not None:
                return reason
        return None


class MaxTurnsChecker:
    """Stop once the loop has run the configured number of turns."""

    def __init__(self, max_turns: int) -> None:
        self._max_turns = max_turns

    def check(self, state: LoopState) -> StopReason | None:
        return StopReason.max_turns if state.turn >= self._max_turns else None


class ConsecutiveFailuresChecker:
    """Stop once tool calls have failed `threshold` times in a row."""

    def __init__(self, threshold: int) -> None:
        self._threshold = threshold

    def check(self, state: LoopState) -> StopReason | None:
        if state.consecutive_failures >= self._threshold:
            return StopReason.consecutive_failures
        return None


class ApprovalRejectedChecker:
    """Stop when a high-risk tool's manual approval was rejected."""

    def check(self, state: LoopState) -> StopReason | None:
        return StopReason.approval_rejected if state.approval_rejected else None
