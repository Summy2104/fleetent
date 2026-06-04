"""Coarse-grained loop detection for the agent loop (AR4).

Registers as a `TerminationChecker` on the AR1 termination framework and reuses
the reserved `loop_detected` reason. It observes the per-run tool-call history on
`LoopState` and flags "calling the same tool over and over without progress" via
two complementary signals (design D2):

- Signal A (exact repeat): the same `(tool_name, arg_fingerprint)` recurs.
- Signal B (result stagnation): the same `tool_name` keeps producing the same
  successful `result_digest`, regardless of whether arguments vary.

The response is two-stage (design D3): the first hit requests a warning be
injected for the model (no termination); if the model ignores it and a signal
hits again, the checker returns `loop_detected` to force-stop. All detection
logic lives here; the loop only records history and injects the warning the
checker requests. No global mutable state; thresholds are injected.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from typing import Any

from fleetent.runtime.termination import LoopState, StopReason

# Bytes kept from each end of a tool result before hashing into a digest. Long
# results are truncated to head+tail so signal-B comparison stays constant-cost
# while still distinguishing substantively different outputs (design D2).
_DIGEST_EDGE_BYTES = 1024


def _window_size(repeat_threshold: int) -> int:
    """History window N derived from the threshold (design D3): N = max(2*t, 6).

    Bound to the threshold rather than separately configurable so the observable
    "how far back a repeat still counts" semantics cannot drift per deployment.
    The window must span both the warning round and the terminating round.
    """
    return max(2 * repeat_threshold, 6)


def arg_fingerprint(arguments: str | dict[str, Any], ignore_keys: Sequence[str] = ()) -> str:
    """Canonical fingerprint of tool-call arguments (design D2, signal A).

    JSON objects are normalized (parse → sort keys → serialize) so semantically
    equal arguments with different key order share a fingerprint. Non-JSON input
    falls back to a fingerprint of its raw string form so malformed data never
    crashes detection. When `ignore_keys` is non-empty those top-level keys are
    dropped before hashing — an opt-in escape hatch, empty by default.
    """
    if isinstance(arguments, str):
        try:
            parsed: Any = json.loads(arguments)
        except (ValueError, TypeError):
            return _hash(arguments)
    else:
        parsed = arguments
    if ignore_keys and isinstance(parsed, dict):
        parsed = {k: v for k, v in parsed.items() if k not in ignore_keys}
    try:
        canonical = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        canonical = str(parsed)
    return _hash(canonical)


def result_digest(result: str) -> str:
    """Digest of a tool result, truncated head+tail before hashing (design D2).

    Only the first and last `_DIGEST_EDGE_BYTES` characters are hashed so digesting
    a huge result is constant-cost. This is a byte-level, not semantic, comparison:
    any substantive change inside the kept edges yields a different digest.
    """
    if len(result) <= 2 * _DIGEST_EDGE_BYTES:
        material = result
    else:
        material = result[:_DIGEST_EDGE_BYTES] + result[-_DIGEST_EDGE_BYTES:]
    return _hash(material)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LoopDetectionChecker:
    """Two-stage loop-detection checker reusing `StopReason.loop_detected`.

    On the first window-level repeat it sets `loop_warning_requested` (the loop
    injects a corrective warning) and returns None. Once a warning has been
    injected, the next repeat returns `StopReason.loop_detected`.
    """

    def __init__(self, repeat_threshold: int, ignore_arg_keys: Sequence[str] = ()) -> None:
        self._threshold = repeat_threshold
        self._ignore_arg_keys = tuple(ignore_arg_keys)

    @property
    def window(self) -> int:
        return _window_size(self._threshold)

    @property
    def ignore_arg_keys(self) -> tuple[str, ...]:
        return self._ignore_arg_keys

    def check(self, state: LoopState) -> StopReason | None:
        if not self._has_repeat(state.tool_history):
            return None
        if state.loop_warning_injected:
            return StopReason.loop_detected
        state.loop_warning_requested = True
        return None

    def _has_repeat(self, history: Sequence[tuple[str, str, str, bool]]) -> bool:
        """True when signal A or signal B reaches the threshold within the window."""
        window = history[-self.window :]
        # Signal A: same (tool_name, arg_fingerprint) recurs.
        signal_a = Counter((tool, fp) for tool, fp, _digest, _ok in window)
        if any(count >= self._threshold for count in signal_a.values()):
            return True
        # Signal B: same tool's successful calls share a result_digest. Failed
        # results are excluded (consecutive_failures already covers those).
        signal_b = Counter((tool, digest) for tool, _fp, digest, ok in window if ok)
        return any(count >= self._threshold for count in signal_b.values())
