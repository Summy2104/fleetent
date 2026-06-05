"""Agent-loop termination framework.

Provides a single, extensible checkpoint for deciding when (and why) the agent
loop must stop. Each termination reason is an independent checker registered on
a `TerminationController`; new reasons (loop detection, budget, cancellation)
plug in by registering a checker rather than editing the loop body.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

LimitConfig = dict[str, int]

# One observed tool call: (tool_name, arg_fingerprint, result_digest, success).
# Carried on LoopState so the loop-detection checker (AR4) can read recent
# history; success gates signal B (only successful, identical results count).
ToolCallRecord = tuple[str, str, str, bool]


def _default_config() -> LimitConfig:
    """Deployment-level defaults from Settings (env-configurable). Lazy import
    mirrors context_mgr._default_config to keep this module import-light."""
    from fleetent.config import Settings

    s = Settings()  # type: ignore[call-arg]
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
    # Retained for compatibility (existing references / historical traces) but no
    # longer produced by the loop: the step dimension is now one of the budget
    # dimensions and surfaces as `budget_exceeded` (AR2 design D2).
    max_turns = "max_turns"
    consecutive_failures = "consecutive_failures"
    approval_rejected = "approval_rejected"
    # Reserved: defined here so trace consumers know the full vocabulary, but no
    # checker is registered for these in this change (see proposal/design).
    loop_detected = "loop_detected"
    budget_exceeded = "budget_exceeded"
    cancelled = "cancelled"
    # A strict-mode MCP server the agent is bound to is unavailable (MCP4): the run
    # stops up front with a clear error rather than proceeding without those tools.
    mcp_strict_unavailable = "mcp_strict_unavailable"


@dataclass
class LoopState:
    """Mutable per-run state the loop updates and termination checkers read."""

    turn: int = 0
    consecutive_failures: int = 0
    approval_rejected: bool = False
    # Loop-detection state (AR4). Defaults keep this backward-compatible: an
    # empty history and unset flags leave every existing checker unaffected.
    tool_history: list[ToolCallRecord] = field(default_factory=list)
    loop_warning_requested: bool = False
    loop_warning_injected: bool = False
    # Per-call guardrail state (AR10): the strict back-to-back repeat streak plus a
    # trip flag the GuardrailChecker reads. Defaults keep this backward-compatible.
    last_call_fingerprint: tuple[str, str] | None = None
    consecutive_repeat: int = 0
    guardrail_tripped: bool = False

    def record_tool_call(
        self,
        tool_name: str,
        arg_fingerprint: str,
        result_digest: str,
        success: bool,
        *,
        window: int,
    ) -> None:
        """Append one tool call and FIFO-truncate the history to `window` entries.

        Keeping only the recent window bounds memory and scopes "how long ago a
        repeat still counts as the same loop" to the detection window (design D3).
        """
        self.tool_history.append((tool_name, arg_fingerprint, result_digest, success))
        if len(self.tool_history) > window:
            del self.tool_history[:-window]


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


class GuardrailChecker:
    """Stop when the per-call tool guardrail tripped (AR10), reusing loop_detected.

    The guardrail runs before dispatch (in the loop body) and sets `guardrail_
    tripped` on its second strict-consecutive hit; this checker turns that flag
    into a `loop_detected` stop at the next checkpoint, like ApprovalRejected.
    """

    def check(self, state: LoopState) -> StopReason | None:
        return StopReason.loop_detected if state.guardrail_tripped else None
