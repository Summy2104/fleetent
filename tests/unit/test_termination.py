"""Unit tests for the agent-loop termination framework."""

from __future__ import annotations

from fleetent.config import Settings
from fleetent.runtime.budget import BudgetChecker, BudgetConfig, BudgetUsage
from fleetent.runtime.termination import (
    ApprovalRejectedChecker,
    ConsecutiveFailuresChecker,
    LoopState,
    StopReason,
    TerminationController,
    resolve_limits,
)

# ── StopReason enum ────────────────────────────────────────────────────────────


def test_stop_reason_active_values_exist() -> None:
    assert StopReason.normal
    assert StopReason.max_turns
    assert StopReason.consecutive_failures
    assert StopReason.approval_rejected


def test_stop_reason_reserved_values_exist() -> None:
    assert StopReason.loop_detected
    assert StopReason.budget_exceeded
    assert StopReason.cancelled


def test_stop_reason_is_str_enum() -> None:
    # str-valued so it serializes cleanly into JSONL traces
    assert isinstance(StopReason.max_turns, str)
    assert StopReason.max_turns == "max_turns"


# ── LoopState ──────────────────────────────────────────────────────────────────


def test_loop_state_defaults() -> None:
    state = LoopState()
    assert state.turn == 0
    assert state.consecutive_failures == 0
    assert state.approval_rejected is False


def test_loop_state_is_mutable() -> None:
    state = LoopState()
    state.turn += 1
    state.consecutive_failures = 2
    state.approval_rejected = True
    assert state.turn == 1
    assert state.consecutive_failures == 2
    assert state.approval_rejected is True


def test_loop_state_loop_detection_fields_default_empty() -> None:
    # Backward-compatible: history empty, warning flags False so existing
    # checkers and callers that never touch them are unaffected.
    state = LoopState()
    assert state.tool_history == []
    assert state.loop_warning_requested is False
    assert state.loop_warning_injected is False


def test_loop_state_tool_history_holds_four_tuples() -> None:
    state = LoopState()
    state.tool_history.append(("read_file", "fp", "digest", True))
    assert state.tool_history == [("read_file", "fp", "digest", True)]


def test_loop_state_history_fifo_truncated_to_window() -> None:
    # FIFO truncation keeps only the most recent `window` entries.
    state = LoopState()
    for i in range(20):
        state.record_tool_call(f"t{i}", "fp", "d", True, window=6)
    assert len(state.tool_history) == 6
    assert state.tool_history[0][0] == "t14"
    assert state.tool_history[-1][0] == "t19"


def test_loop_state_record_tool_call_appends() -> None:
    state = LoopState()
    state.record_tool_call("read_file", "fp-x", "d1", True, window=6)
    assert state.tool_history == [("read_file", "fp-x", "d1", True)]


# ── TerminationController ───────────────────────────────────────────────────────


class _StubChecker:
    def __init__(self, reason: StopReason | None) -> None:
        self._reason = reason
        self.calls = 0

    def check(self, state: LoopState) -> StopReason | None:
        self.calls += 1
        return self._reason


def test_controller_no_checker_returns_none() -> None:
    controller = TerminationController()
    assert controller.should_stop(LoopState()) is None


def test_controller_registered_checker_is_called() -> None:
    checker = _StubChecker(None)
    controller = TerminationController()
    controller.register(checker)
    controller.should_stop(LoopState())
    assert checker.calls == 1


def test_controller_returns_first_non_none_reason() -> None:
    controller = TerminationController()
    controller.register(_StubChecker(None))
    controller.register(_StubChecker(StopReason.max_turns))
    controller.register(_StubChecker(StopReason.consecutive_failures))
    assert controller.should_stop(LoopState()) == StopReason.max_turns


def test_controller_short_circuits_after_first_hit() -> None:
    first = _StubChecker(StopReason.max_turns)
    second = _StubChecker(StopReason.consecutive_failures)
    controller = TerminationController()
    controller.register(first)
    controller.register(second)
    controller.should_stop(LoopState())
    assert first.calls == 1
    assert second.calls == 0


# ── config / resolve_limits ─────────────────────────────────────────────────────


def test_settings_has_termination_fields_with_defaults() -> None:
    # Verified via model_fields to avoid instantiating Settings (needs api key)
    assert Settings.model_fields["agent_max_turns"].default == 50
    assert Settings.model_fields["agent_max_consecutive_failures"].default == 3


def test_resolve_limits_uses_config_when_no_params() -> None:
    limits = resolve_limits(
        config={"max_turns": 50, "max_consecutive_failures": 3},
    )
    assert limits == (50, 3)


def test_resolve_limits_call_params_override_config() -> None:
    limits = resolve_limits(
        max_turns=10,
        max_consecutive_failures=7,
        config={"max_turns": 50, "max_consecutive_failures": 3},
    )
    assert limits == (10, 7)


def test_resolve_limits_partial_override() -> None:
    limits = resolve_limits(
        max_turns=10,
        config={"max_turns": 50, "max_consecutive_failures": 3},
    )
    assert limits == (10, 3)


# ── step dimension carried by BudgetChecker (AR2; MaxTurnsChecker retired) ──────
#
# The step dimension is now one of the three budget dimensions. Reaching the turn
# cap surfaces as StopReason.budget_exceeded (not max_turns), produced by
# BudgetChecker reading BudgetUsage.turns. StopReason.max_turns is retained as an
# enum member (compat / historical traces) but the loop no longer produces it.


def _step_budget(max_turns: int) -> BudgetConfig:
    return BudgetConfig(max_turns=max_turns, max_tokens=-1)


def test_step_budget_stops_at_limit() -> None:
    checker = BudgetChecker(_step_budget(3), BudgetUsage(turns=3))
    assert checker.check(LoopState()) == StopReason.budget_exceeded
    assert checker.triggered_dimension == "turns"


def test_step_budget_stops_above_limit() -> None:
    checker = BudgetChecker(_step_budget(3), BudgetUsage(turns=4))
    assert checker.check(LoopState()) == StopReason.budget_exceeded


def test_step_budget_passes_below_limit() -> None:
    checker = BudgetChecker(_step_budget(3), BudgetUsage(turns=2))
    assert checker.check(LoopState()) is None


def test_stop_reason_max_turns_member_retained_for_compat() -> None:
    # Retained so historical traces and existing references stay readable, even
    # though the loop no longer produces it (design D2).
    assert StopReason.max_turns == "max_turns"


# ── ConsecutiveFailuresChecker ──────────────────────────────────────────────────


def test_consecutive_failures_checker_stops_at_threshold() -> None:
    checker = ConsecutiveFailuresChecker(threshold=3)
    assert checker.check(LoopState(consecutive_failures=3)) == StopReason.consecutive_failures


def test_consecutive_failures_checker_passes_below_threshold() -> None:
    checker = ConsecutiveFailuresChecker(threshold=3)
    assert checker.check(LoopState(consecutive_failures=2)) is None


# ── ApprovalRejectedChecker ─────────────────────────────────────────────────────


def test_approval_rejected_checker_stops_when_flagged() -> None:
    checker = ApprovalRejectedChecker()
    assert checker.check(LoopState(approval_rejected=True)) == StopReason.approval_rejected


def test_approval_rejected_checker_passes_when_not_flagged() -> None:
    checker = ApprovalRejectedChecker()
    assert checker.check(LoopState(approval_rejected=False)) is None
