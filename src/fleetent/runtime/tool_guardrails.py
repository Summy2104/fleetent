"""Per-call tool guardrail: strict back-to-back repeat detection (AR10).

A finer-grained complement to AR4's window-based loop detection. AR4 reads the
recent history *after* a turn; this guard runs *before* dispatch and counts how
many times the identical `(tool, arg_fingerprint)` was called strictly
back-to-back. On the Nth consecutive identical call it short-circuits (skips the
redundant execution and feeds a correction back); if the model repeats yet again
it stops the run. Parameter comparison reuses `loop_detector.arg_fingerprint`,
so "same call" means exactly what AR4 means. State lives on the per-run
`LoopState` — no global mutable state.
"""

from __future__ import annotations

from enum import Enum, auto

from fleetent.runtime.termination import LoopState
from fleetent.structured_logging import get_logger

_logger = get_logger("runtime.guardrails")


class GuardrailAction(Enum):
    proceed = auto()  # below threshold — dispatch normally
    short_circuit = auto()  # Nth consecutive, not yet warned — skip + feed correction
    stop = auto()  # already warned and repeated again — terminate the run


def evaluate_guardrail(
    state: LoopState, tool_name: str, fingerprint: str, threshold: int
) -> GuardrailAction:
    """Update the consecutive-repeat streak on `state` and decide the action.

    Same `(tool, fingerprint)` as the immediately previous call extends the
    streak; anything different resets it to 1. At/over `threshold` the first hit
    short-circuits and the next (post-warning) hit stops.
    """
    key = (tool_name, fingerprint)
    if key == state.last_call_fingerprint:
        state.consecutive_repeat += 1
    else:
        state.last_call_fingerprint = key
        state.consecutive_repeat = 1

    if state.consecutive_repeat < threshold:
        return GuardrailAction.proceed
    if state.loop_warning_injected:
        _logger.error(
            "guardrail_stop", tool_name=tool_name, consecutive_count=state.consecutive_repeat
        )
        return GuardrailAction.stop
    _logger.warn(
        "guardrail_short_circuit",
        tool_name=tool_name,
        consecutive_count=state.consecutive_repeat,
    )
    return GuardrailAction.short_circuit
