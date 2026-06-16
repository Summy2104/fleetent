"""Unit tests: structured logging calls in agent_lifecycle and im_gateway modules."""

from __future__ import annotations

# ── agent_lifecycle.materialize ───────────────────────────────────────────────


def test_materialize_logger_is_custom() -> None:
    import fleetent.platform.agent_lifecycle.materialize as mod
    from fleetent.structured_logging import Logger

    assert isinstance(mod._logger, Logger)


# ── im_gateway.slack ──────────────────────────────────────────────────────────


def test_slack_supervisor_logger_is_custom() -> None:
    import fleetent.im_gateway.slack_supervisor as mod
    from fleetent.structured_logging import Logger

    assert isinstance(mod._logger, Logger)
