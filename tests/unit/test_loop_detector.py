"""Unit tests for the loop-detection checker and its fingerprint helpers."""

from __future__ import annotations

from fleetent.runtime.loop_detector import (
    LoopDetectionChecker,
    arg_fingerprint,
    result_digest,
)
from fleetent.runtime.termination import LoopState, StopReason

# ── arg_fingerprint ─────────────────────────────────────────────────────────


def test_arg_fingerprint_key_order_invariant() -> None:
    a = arg_fingerprint('{"a": 1, "b": 2}')
    b = arg_fingerprint('{"b": 2, "a": 1}')
    assert a == b


def test_arg_fingerprint_accepts_dict_and_str_equivalently() -> None:
    assert arg_fingerprint({"a": 1, "b": 2}) == arg_fingerprint('{"b": 2, "a": 1}')


def test_arg_fingerprint_different_args_differ() -> None:
    assert arg_fingerprint('{"a": 1}') != arg_fingerprint('{"a": 2}')


def test_arg_fingerprint_invalid_json_falls_back_to_raw() -> None:
    # Non-JSON: same raw string → same fingerprint; different raw → different.
    assert arg_fingerprint("not json") == arg_fingerprint("not json")
    assert arg_fingerprint("not json") != arg_fingerprint("other raw")


def test_arg_fingerprint_ignore_keys_removed_before_hashing() -> None:
    with_ts = arg_fingerprint('{"q": "x", "ts": 111}', ignore_keys=["ts"])
    other_ts = arg_fingerprint('{"q": "x", "ts": 999}', ignore_keys=["ts"])
    assert with_ts == other_ts


def test_arg_fingerprint_ignore_keys_empty_keeps_all() -> None:
    a = arg_fingerprint('{"q": "x", "ts": 111}', ignore_keys=[])
    b = arg_fingerprint('{"q": "x", "ts": 999}', ignore_keys=[])
    assert a != b


# ── result_digest ───────────────────────────────────────────────────────────


def test_result_digest_stable_for_identical_results() -> None:
    assert result_digest("same") == result_digest("same")


def test_result_digest_differs_for_substantive_change() -> None:
    assert result_digest("alpha") != result_digest("beta")


def test_result_digest_empty_has_deterministic_value() -> None:
    assert result_digest("") == result_digest("")


def test_result_digest_truncates_long_middle() -> None:
    # Same head + tail, different (huge) middle beyond the truncation window →
    # same digest, because only the first/last 1KB are hashed.
    head = "H" * 1024
    tail = "T" * 1024
    a = head + ("X" * 100_000) + tail
    b = head + ("Y" * 100_000) + tail
    assert result_digest(a) == result_digest(b)


def test_result_digest_distinguishes_within_truncation_window() -> None:
    short_a = "abc"
    short_b = "abd"
    assert result_digest(short_a) != result_digest(short_b)


# ── LoopDetectionChecker: signal A (exact-repeat) + stage one (warn) ─────────


def _append(state: LoopState, tool: str, fp: str, digest: str, success: bool = True) -> None:
    state.tool_history.append((tool, fp, digest, success))


def test_signal_a_first_hit_requests_warning_not_stop() -> None:
    checker = LoopDetectionChecker(repeat_threshold=3)
    state = LoopState()
    for _ in range(3):
        _append(state, "read_file", "fp-x", "d1")
    reason = checker.check(state)
    assert reason is None  # not loop_detected on first hit
    assert state.loop_warning_requested is True


def test_signal_a_below_threshold_no_action() -> None:
    checker = LoopDetectionChecker(repeat_threshold=3)
    state = LoopState()
    for _ in range(2):
        _append(state, "read_file", "fp-x", "d1")
    assert checker.check(state) is None
    assert state.loop_warning_requested is False


# ── signal B (result stagnation) ─────────────────────────────────────────────


def test_signal_b_same_result_different_args_requests_warning() -> None:
    checker = LoopDetectionChecker(repeat_threshold=3)
    state = LoopState()
    # Different arg fingerprints each time, but identical success result digest.
    for i in range(3):
        _append(state, "search", f"fp-{i}", "same-digest", success=True)
    assert checker.check(state) is None
    assert state.loop_warning_requested is True


def test_signal_b_ignores_failed_results() -> None:
    checker = LoopDetectionChecker(repeat_threshold=3)
    state = LoopState()
    for i in range(3):
        _append(state, "search", f"fp-{i}", "same-digest", success=False)
    assert checker.check(state) is None
    assert state.loop_warning_requested is False


def test_signal_b_differing_results_no_action() -> None:
    checker = LoopDetectionChecker(repeat_threshold=3)
    state = LoopState()
    for i in range(3):
        _append(state, "search", f"fp-{i}", f"digest-{i}", success=True)
    assert checker.check(state) is None
    assert state.loop_warning_requested is False


# ── stage two (terminate) ─────────────────────────────────────────────────────


def test_stage_two_terminates_after_warning_injected() -> None:
    checker = LoopDetectionChecker(repeat_threshold=3)
    state = LoopState()
    state.loop_warning_injected = True  # warning already delivered to the model
    for _ in range(3):
        _append(state, "read_file", "fp-x", "d1")
    assert checker.check(state) == StopReason.loop_detected


def test_stage_two_signal_b_terminates_after_warning() -> None:
    checker = LoopDetectionChecker(repeat_threshold=3)
    state = LoopState()
    state.loop_warning_injected = True
    for i in range(3):
        _append(state, "search", f"fp-{i}", "same-digest", success=True)
    assert checker.check(state) == StopReason.loop_detected


def test_no_repetition_never_triggers() -> None:
    checker = LoopDetectionChecker(repeat_threshold=3)
    state = LoopState()
    state.loop_warning_injected = True
    for i in range(6):
        _append(state, f"tool-{i}", f"fp-{i}", f"digest-{i}", success=True)
    assert checker.check(state) is None


# ── threshold injection + ignore keys ─────────────────────────────────────────


def test_small_threshold_changes_hit_count() -> None:
    checker = LoopDetectionChecker(repeat_threshold=2)
    state = LoopState()
    for _ in range(2):
        _append(state, "read_file", "fp-x", "d1")
    assert checker.check(state) is None
    assert state.loop_warning_requested is True
