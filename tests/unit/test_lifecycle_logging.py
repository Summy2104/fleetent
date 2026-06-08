"""Unit tests: structured logging calls in agent_lifecycle and im_gateway modules."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ── agent_lifecycle.controller ────────────────────────────────────────────────


def test_controller_logger_is_custom() -> None:
    import fleetent.platform.agent_lifecycle.controller as mod
    from fleetent.structured_logging import Logger

    assert isinstance(mod._logger, Logger)


def test_controller_logs_info_on_start() -> None:
    from fleetent.platform.agent_lifecycle.controller import AgentController

    fake_proc = MagicMock()
    fake_proc.pid = 1234
    ctrl = AgentController(spawn=lambda name: fake_proc)

    with patch("fleetent.platform.agent_lifecycle.controller._logger") as mock_log:
        ctrl.start("support")

    mock_log.info.assert_called_once()
    kw = mock_log.info.call_args.kwargs
    assert kw["name"] == "support"
    assert kw["pid"] == 1234


def test_controller_logs_info_on_stop() -> None:
    from fleetent.platform.agent_lifecycle.controller import AgentController

    fake_proc = MagicMock()
    fake_proc.pid = 1234
    fake_proc.poll.return_value = None
    ctrl = AgentController(spawn=lambda name: fake_proc)
    ctrl.start("support")

    with patch("fleetent.platform.agent_lifecycle.controller._logger") as mock_log:
        ctrl.stop("support")

    mock_log.info.assert_called_once()
    kw = mock_log.info.call_args.kwargs
    assert kw["name"] == "support"


def test_controller_logs_warn_on_stop_not_tracked() -> None:
    from fleetent.platform.agent_lifecycle.controller import AgentController

    ctrl = AgentController(spawn=lambda name: MagicMock())

    with patch("fleetent.platform.agent_lifecycle.controller._logger") as mock_log:
        ctrl.stop("unknown-agent")

    mock_log.warn.assert_called_once()
    kw = mock_log.warn.call_args.kwargs
    assert kw["name"] == "unknown-agent"


def test_controller_logs_warn_on_duplicate_start() -> None:
    from fleetent.platform.agent_lifecycle.controller import AgentController

    fake_proc = MagicMock()
    fake_proc.pid = 99
    fake_proc.poll.return_value = None
    ctrl = AgentController(spawn=lambda name: fake_proc)
    ctrl.start("support")

    with patch("fleetent.platform.agent_lifecycle.controller._logger") as mock_log:
        ctrl.start("support")

    mock_log.warn.assert_called_once()
    kw = mock_log.warn.call_args.kwargs
    assert kw["name"] == "support"
    assert kw["existing_pid"] == 99


# ── agent_lifecycle.materialize ───────────────────────────────────────────────


def test_materialize_logger_is_custom() -> None:
    import fleetent.platform.agent_lifecycle.materialize as mod
    from fleetent.structured_logging import Logger

    assert isinstance(mod._logger, Logger)


# ── agent_lifecycle.api ───────────────────────────────────────────────────────


def test_lifecycle_api_logger_is_custom() -> None:
    import fleetent.platform.agent_lifecycle.lifecycle_admin_api as mod
    from fleetent.structured_logging import Logger

    assert isinstance(mod._logger, Logger)


# ── im_gateway.slack ──────────────────────────────────────────────────────────


def test_slack_supervisor_logger_is_custom() -> None:
    import fleetent.im_gateway.slack_supervisor as mod
    from fleetent.structured_logging import Logger

    assert isinstance(mod._logger, Logger)
