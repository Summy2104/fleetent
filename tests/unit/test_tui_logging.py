"""Unit tests: structured logging calls in TUI modules."""

from __future__ import annotations

from unittest.mock import patch

# ── tui.transport ─────────────────────────────────────────────────────────────


def test_transport_logger_is_custom() -> None:
    import fleetent.tui.transport as mod
    from fleetent.structured_logging import Logger

    assert isinstance(mod._logger, Logger)


async def test_transport_warns_on_close_error() -> None:

    from fleetent.tui.transport import WSTransport

    class BadCloseWS:
        async def send_text(self, _: str) -> None:
            pass

        async def close(self, code: int = 1000) -> None:
            raise RuntimeError("unexpected serialization failure")

    t = WSTransport(BadCloseWS())

    with patch("fleetent.tui.transport._logger") as mock_log:
        await t.close()

    mock_log.warn.assert_called_once()
    kw = mock_log.warn.call_args.kwargs
    assert "error" in kw


# ── tui.backend ───────────────────────────────────────────────────────────────


def test_backend_logger_is_custom() -> None:
    import fleetent.tui.backend as mod
    from fleetent.structured_logging import Logger

    assert isinstance(mod._logger, Logger)


# ── tui.dispatch ──────────────────────────────────────────────────────────────


def test_dispatch_logger_is_custom() -> None:
    import fleetent.tui.dispatch as mod
    from fleetent.structured_logging import Logger

    assert isinstance(mod._logger, Logger)


# ── tui.app ───────────────────────────────────────────────────────────────────


def test_app_logger_is_custom() -> None:
    import fleetent.tui.app as mod
    from fleetent.structured_logging import Logger

    assert isinstance(mod._logger, Logger)
