"""Unit tests: structured logging calls in agent runtime modules.

Each test patches the module-level _logger and asserts the correct level/event
is emitted. Tests are grouped by module.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ── runtime.budget ────────────────────────────────────────────────────────────


def test_budget_checker_warns_on_turns_exhaustion() -> None:
    from fleetent.runtime.budget import NO_LIMIT, BudgetChecker, BudgetConfig, BudgetUsage

    config = BudgetConfig(max_turns=1, max_tokens=NO_LIMIT)
    usage = BudgetUsage(turns=1)
    checker = BudgetChecker(config, usage)

    with patch("fleetent.runtime.budget._logger") as mock_log:
        checker.check(MagicMock())

    mock_log.warn.assert_called_once()
    kw = mock_log.warn.call_args.kwargs
    assert kw["dimension"] == "turns"
    assert kw["limit"] == 1
    assert kw["actual"] == 1


def test_budget_checker_warns_on_tokens_exhaustion() -> None:
    from fleetent.runtime.budget import NO_LIMIT, BudgetChecker, BudgetConfig, BudgetUsage

    config = BudgetConfig(max_turns=NO_LIMIT, max_tokens=100)
    usage = BudgetUsage(turns=5, tokens=100)
    checker = BudgetChecker(config, usage)

    with patch("fleetent.runtime.budget._logger") as mock_log:
        checker.check(MagicMock())

    mock_log.warn.assert_called_once()
    kw = mock_log.warn.call_args.kwargs
    assert kw["dimension"] == "tokens"


def test_budget_checker_no_log_when_within_budget() -> None:
    from fleetent.runtime.budget import BudgetChecker, BudgetConfig, BudgetUsage

    config = BudgetConfig(max_turns=10, max_tokens=1000)
    usage = BudgetUsage(turns=1, tokens=50)
    checker = BudgetChecker(config, usage)

    with patch("fleetent.runtime.budget._logger") as mock_log:
        checker.check(MagicMock())

    mock_log.warn.assert_not_called()


# ── runtime.snapshot ─────────────────────────────────────────────────────────


def test_snapshot_load_active_logs_info_on_success() -> None:
    from fleetent.runtime import snapshot

    fake_snap = MagicMock()
    fake_snap.version_id = 7

    with (
        patch("fleetent.runtime.snapshot._logger") as mock_log,
        patch("fleetent.runtime.snapshot.agent_config.current") as mock_idx,
    ):
        mock_agent = MagicMock()
        mock_idx.return_value.get.return_value = mock_agent
        with patch("fleetent.runtime.snapshot._snapshot_from_file", return_value=fake_snap):
            snapshot.load_active("support")

    mock_log.info.assert_called_once()
    kw = mock_log.info.call_args.kwargs
    assert kw["agent"] == "support"


def test_snapshot_load_active_logs_warn_when_not_found() -> None:
    from fleetent.runtime import snapshot

    with (
        patch("fleetent.runtime.snapshot._logger") as mock_log,
        patch("fleetent.runtime.snapshot.agent_config.current") as mock_idx,
    ):
        mock_idx.return_value.get.return_value = None
        snapshot.load_active("missing-agent")

    mock_log.warn.assert_called_once()
    kw = mock_log.warn.call_args.kwargs
    assert kw["agent"] == "missing-agent"


# ── runtime.loop_detector ────────────────────────────────────────────────────


def test_loop_detector_warns_on_first_signal() -> None:
    from fleetent.runtime.loop_detector import LoopDetectionChecker, arg_fingerprint
    from fleetent.runtime.termination import LoopState

    checker = LoopDetectionChecker(repeat_threshold=2)
    state = LoopState()
    fp = arg_fingerprint("{}")

    # Build up to detection threshold (first hit = warn, not stop)
    for _ in range(2):
        state.record_tool_call("same_tool", fp, "digest1", True, window=checker.window)

    with patch("fleetent.runtime.loop_detector._logger") as mock_log:
        checker.check(state)

    mock_log.warn.assert_called_once()
    kw = mock_log.warn.call_args.kwargs
    assert "tool_name" in kw


def test_loop_detector_errors_on_second_signal() -> None:
    from fleetent.runtime.loop_detector import LoopDetectionChecker, arg_fingerprint
    from fleetent.runtime.termination import LoopState

    checker = LoopDetectionChecker(repeat_threshold=2)
    state = LoopState()
    fp = arg_fingerprint("{}")

    for _ in range(2):
        state.record_tool_call("same_tool", fp, "digest1", True, window=checker.window)

    # First check injects warning
    checker.check(state)
    state.loop_warning_injected = True

    # Add another record and check again - should produce error log + stop
    state.record_tool_call("same_tool", fp, "digest1", True, window=checker.window)

    with patch("fleetent.runtime.loop_detector._logger") as mock_log:
        checker.check(state)

    mock_log.error.assert_called_once()
    kw = mock_log.error.call_args.kwargs
    assert "tool_name" in kw


# ── runtime.guardrails ───────────────────────────────────────────────────────


def test_guardrails_warns_on_short_circuit() -> None:
    from fleetent.runtime.loop_detector import arg_fingerprint
    from fleetent.runtime.termination import LoopState
    from fleetent.runtime.tool_guardrails import GuardrailAction, evaluate_guardrail

    state = LoopState()
    fp = arg_fingerprint("{}")

    with patch("fleetent.runtime.tool_guardrails._logger") as mock_log:
        evaluate_guardrail(state, "my_tool", fp, 3)  # 1
        evaluate_guardrail(state, "my_tool", fp, 3)  # 2
        action = evaluate_guardrail(state, "my_tool", fp, 3)  # 3 → short_circuit

    assert action is GuardrailAction.short_circuit
    mock_log.warn.assert_called_once()
    kw = mock_log.warn.call_args.kwargs
    assert kw["tool_name"] == "my_tool"
    assert kw["consecutive_count"] == 3


def test_guardrails_errors_on_stop() -> None:
    from fleetent.runtime.loop_detector import arg_fingerprint
    from fleetent.runtime.termination import LoopState
    from fleetent.runtime.tool_guardrails import GuardrailAction, evaluate_guardrail

    state = LoopState()
    fp = arg_fingerprint("{}")

    # reach threshold
    for _ in range(3):
        evaluate_guardrail(state, "my_tool", fp, 3)
    state.loop_warning_injected = True  # mark warned

    with patch("fleetent.runtime.tool_guardrails._logger") as mock_log:
        action = evaluate_guardrail(state, "my_tool", fp, 3)  # stop

    assert action is GuardrailAction.stop
    mock_log.error.assert_called_once()
    kw = mock_log.error.call_args.kwargs
    assert kw["tool_name"] == "my_tool"


def test_guardrails_no_log_when_below_threshold() -> None:
    from fleetent.runtime.loop_detector import arg_fingerprint
    from fleetent.runtime.termination import LoopState
    from fleetent.runtime.tool_guardrails import evaluate_guardrail

    state = LoopState()
    fp = arg_fingerprint("{}")

    with patch("fleetent.runtime.tool_guardrails._logger") as mock_log:
        evaluate_guardrail(state, "my_tool", fp, 3)
        evaluate_guardrail(state, "my_tool", fp, 3)

    mock_log.warn.assert_not_called()
    mock_log.error.assert_not_called()


# ── runtime.hygiene ──────────────────────────────────────────────────────────


def test_hygiene_warns_when_repairs_made() -> None:
    from fleetent.runtime.message_hygiene import sanitize

    # Consecutive same-role messages will trigger a repair
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "user", "content": "world"},
    ]

    with patch("fleetent.runtime.message_hygiene._logger") as mock_log:
        sanitize(msgs)

    mock_log.warn.assert_called_once()
    kw = mock_log.warn.call_args.kwargs
    assert "repairs" in kw


def test_hygiene_no_log_when_no_repairs() -> None:
    from fleetent.runtime.message_hygiene import sanitize

    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]

    with patch("fleetent.runtime.message_hygiene._logger") as mock_log:
        sanitize(msgs)

    mock_log.warn.assert_not_called()


# ── runtime.error ────────────────────────────────────────────────────────────


def test_error_classifier_logs_debug_on_classify() -> None:
    from fleetent.runtime.error_classifier import classify

    exc = Exception("something went wrong")

    with patch("fleetent.runtime.error_classifier._logger") as mock_log:
        classify(exc)

    mock_log.debug.assert_called_once()
    kw = mock_log.debug.call_args.kwargs
    assert "category" in kw
    assert "should_retry" in kw
    assert "should_compress" in kw
    assert "should_switch_model" in kw


# ── runtime.loop (existing structlog → custom) ───────────────────────────────


def test_loop_logger_is_custom_not_structlog() -> None:
    import fleetent.runtime.loop as loop_mod
    from fleetent.observability.structured_logging import Logger

    assert isinstance(loop_mod._logger, Logger)


def test_loop_has_no_structlog_import() -> None:
    import ast
    import pathlib

    src = pathlib.Path("src/fleetent/runtime/loop.py").read_text()
    tree = ast.parse(src)
    structlog_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and any(
            (getattr(a, "name", None) or getattr(node, "module", None) or "").startswith(
                "structlog"
            )
            for a in getattr(node, "names", [{"name": ""}])
        )
    ]
    assert structlog_imports == [], "loop.py must not import structlog"


# ── runtime.context (existing structlog → custom) ────────────────────────────


def test_context_logger_is_custom_not_structlog() -> None:
    import fleetent.runtime.context as ctx_mod
    from fleetent.observability.structured_logging import Logger

    assert isinstance(ctx_mod._logger, Logger)


# ── runtime.sub_agent (existing stdlib → custom) ─────────────────────────────


def test_sub_agent_logger_is_custom_not_stdlib() -> None:
    import fleetent.runtime.sub_agent as sa_mod
    from fleetent.observability.structured_logging import Logger

    assert isinstance(sa_mod._logger, Logger)


def test_sub_agent_lifecycle_logger_is_custom_not_stdlib() -> None:
    import fleetent.runtime.sub_agent_lifecycle as sal_mod
    from fleetent.observability.structured_logging import Logger

    assert isinstance(sal_mod._logger, Logger)


# ── runtime.agent_app (existing structlog → custom) ──────────────────────────


def test_agent_app_logger_is_custom_not_structlog() -> None:
    import fleetent.runtime.agent_app as app_mod
    from fleetent.observability.structured_logging import Logger

    assert isinstance(app_mod._logger, Logger)
