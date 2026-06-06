"""Unit tests: structured logging calls in sandbox modules."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

# ── sandbox.client ────────────────────────────────────────────────────────────


def test_sandbox_client_logger_is_custom() -> None:
    import fleetent.integrations.sandbox.client as mod
    from fleetent.observability.structured_logging import Logger

    assert isinstance(mod._logger, Logger)


async def test_sandbox_client_logs_info_on_create() -> None:
    from fleetent.integrations.sandbox.client import SandboxClient
    from fleetent.integrations.sandbox.config import SandboxResources

    client = SandboxClient(image="python:3.12-slim")
    fake_id = "abc123def456\n"

    with (
        patch("asyncio.create_subprocess_exec", AsyncMock(return_value=_mock_proc(stdout=fake_id))),
        patch("fleetent.integrations.sandbox.client._logger") as mock_log,
    ):
        await client.create_workspace("session-1", resources=SandboxResources())

    mock_log.info.assert_called()
    call_args = mock_log.info.call_args
    assert "container_id" in call_args.kwargs


async def test_sandbox_client_logs_warn_on_docker_probe_fail() -> None:
    from fleetent.integrations.sandbox.client import SandboxClient

    client = SandboxClient(image="python:3.12-slim")

    with (
        patch(
            "asyncio.create_subprocess_exec",
            AsyncMock(return_value=_mock_proc(stderr="not found", returncode=1)),
        ),
        patch("fleetent.integrations.sandbox.client._logger") as mock_log,
    ):
        await client.docker_available()

    mock_log.warn.assert_called()


# ── sandbox.config ────────────────────────────────────────────────────────────


def test_sandbox_config_logger_is_custom() -> None:
    import fleetent.integrations.sandbox.config as mod
    from fleetent.observability.structured_logging import Logger

    assert isinstance(mod._logger, Logger)


def test_sandbox_config_warns_on_invalid_scope() -> None:
    from fleetent.integrations.sandbox.config import _load_scope

    with patch("fleetent.integrations.sandbox.config._logger") as mock_log:
        _load_scope({"scope": "invalid_scope_xyz"}, "session")

    mock_log.warn.assert_called_once()


# ── sandbox.cleanup ───────────────────────────────────────────────────────────


def test_sandbox_cleanup_logger_is_custom() -> None:
    import fleetent.integrations.sandbox.cleanup as mod
    from fleetent.observability.structured_logging import Logger

    assert isinstance(mod._logger, Logger)


# ── sandbox.enablement ────────────────────────────────────────────────────────


def test_sandbox_enablement_logger_is_custom() -> None:
    import fleetent.integrations.sandbox.enablement as mod
    from fleetent.observability.structured_logging import Logger

    assert isinstance(mod._logger, Logger)


def test_sandbox_enablement_warns_on_invalid_mode() -> None:
    from fleetent.integrations.sandbox.enablement import load_sandbox_mode

    with (
        patch("fleetent.integrations.sandbox.enablement._logger") as mock_log,
        patch(
            "fleetent.integrations.sandbox.enablement._read_raw_mode",
            return_value="not_a_real_mode",
        ),
    ):
        load_sandbox_mode()

    mock_log.warn.assert_called_once()


# ── helpers ───────────────────────────────────────────────────────────────────


def _mock_proc(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout.encode(), stderr.encode()))
    return proc
