"""Tests for the per-call tool guardrail: strict consecutive-repeat (AR10)."""

from fleetent.runtime.loop_detector import arg_fingerprint
from fleetent.runtime.termination import GuardrailChecker, LoopState, StopReason
from fleetent.runtime.tool_guardrails import GuardrailAction, evaluate_guardrail


def _fp(args: str) -> str:
    return arg_fingerprint(args, [])


# ── threshold default + resolution (group 2) ─────────────────────────────────


def test_agentfile_guardrail_threshold_default_3():
    from fleetent.agent_config import AgentFile, default_models

    assert AgentFile(name="x", version=1, models=default_models()).guardrail_repeat_threshold == 3


# ── strict consecutive counting + trigger (group 3) ──────────────────────────


def test_two_consecutive_below_threshold_proceeds():
    st = LoopState()
    fp = _fp("{}")
    assert evaluate_guardrail(st, "t", fp, 3) is GuardrailAction.proceed
    assert evaluate_guardrail(st, "t", fp, 3) is GuardrailAction.proceed


def test_third_consecutive_short_circuits():
    st = LoopState()
    fp = _fp("{}")
    evaluate_guardrail(st, "t", fp, 3)
    evaluate_guardrail(st, "t", fp, 3)
    assert evaluate_guardrail(st, "t", fp, 3) is GuardrailAction.short_circuit


def test_different_call_in_middle_resets_count():
    st = LoopState()
    fp_a, fp_b = _fp('{"a":1}'), _fp('{"b":2}')
    evaluate_guardrail(st, "t", fp_a, 3)  # 1
    evaluate_guardrail(st, "t", fp_a, 3)  # 2
    evaluate_guardrail(st, "t", fp_b, 3)  # different → reset to 1
    assert evaluate_guardrail(st, "t", fp_a, 3) is GuardrailAction.proceed  # back to 1


def test_after_warning_repeat_stops():
    st = LoopState()
    fp = _fp("{}")
    evaluate_guardrail(st, "t", fp, 3)
    evaluate_guardrail(st, "t", fp, 3)
    assert evaluate_guardrail(st, "t", fp, 3) is GuardrailAction.short_circuit
    st.loop_warning_injected = True  # agent_loop sets this on short_circuit
    assert evaluate_guardrail(st, "t", fp, 3) is GuardrailAction.stop


def test_json_key_order_counts_as_same_call():
    st = LoopState()
    # Different key order but semantically identical → same fingerprint → same streak.
    evaluate_guardrail(st, "t", _fp('{"a":1,"b":2}'), 3)
    evaluate_guardrail(st, "t", _fp('{"b":2,"a":1}'), 3)
    assert evaluate_guardrail(st, "t", _fp('{"a":1,"b":2}'), 3) is GuardrailAction.short_circuit


def test_different_tool_same_args_not_same_streak():
    st = LoopState()
    fp = _fp("{}")
    evaluate_guardrail(st, "tool_a", fp, 3)
    evaluate_guardrail(st, "tool_a", fp, 3)
    # Different tool name resets even with identical args.
    assert evaluate_guardrail(st, "tool_b", fp, 3) is GuardrailAction.proceed


# ── GuardrailChecker → loop_detected (group 4) ───────────────────────────────


def test_guardrail_checker_stops_when_tripped():
    st = LoopState()
    st.guardrail_tripped = True
    assert GuardrailChecker().check(st) is StopReason.loop_detected


def test_guardrail_checker_none_when_not_tripped():
    assert GuardrailChecker().check(LoopState()) is None
