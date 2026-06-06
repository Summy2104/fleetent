"""_start_infra wires sandbox orphan-cleanup + idle-sweep into agent runtime boot.

All collaborators are mocked (no real Docker / asyncio tasks / MCP), keeping this
single-module behavioural test at unit level.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fleetent.integrations.sandbox import Mode
from fleetent.runtime import agent_app


def _agent_without_mcp() -> MagicMock:
    agent = MagicMock()
    agent.mcp_servers = []
    return agent


async def test_start_infra_cleans_orphans_and_starts_sweep_when_docker_available() -> None:
    with (
        patch(
            "fleetent.integrations.sandbox.enablement.get_effective_mode",
            AsyncMock(return_value=Mode.ALL),
        ),
        patch("fleetent.integrations.sandbox.cleanup_orphans", AsyncMock()) as cleanup,
        patch("fleetent.integrations.sandbox.start_idle_sweep") as sweep,
        patch("fleetent.integrations.sandbox.SandboxClient"),
        patch("fleetent.session.manager.start_session_maintenance"),
    ):
        await agent_app._start_infra(_agent_without_mcp())

    cleanup.assert_awaited_once()
    sweep.assert_called_once()


async def test_start_infra_skips_sandbox_lifecycle_when_docker_unavailable() -> None:
    with (
        patch(
            "fleetent.integrations.sandbox.enablement.get_effective_mode",
            AsyncMock(return_value=Mode.OFF),
        ),
        patch("fleetent.integrations.sandbox.cleanup_orphans", AsyncMock()) as cleanup,
        patch("fleetent.integrations.sandbox.start_idle_sweep") as sweep,
        patch("fleetent.session.manager.start_session_maintenance"),
    ):
        await agent_app._start_infra(_agent_without_mcp())

    cleanup.assert_not_awaited()
    sweep.assert_not_called()


async def test_start_infra_cleanup_failure_does_not_block_startup() -> None:
    """An orphan-cleanup error is logged; boot still proceeds to session maintenance."""
    with (
        patch(
            "fleetent.integrations.sandbox.enablement.get_effective_mode",
            AsyncMock(return_value=Mode.ALL),
        ),
        patch(
            "fleetent.integrations.sandbox.cleanup_orphans",
            AsyncMock(side_effect=RuntimeError("docker boom")),
        ),
        patch("fleetent.integrations.sandbox.start_idle_sweep"),
        patch("fleetent.integrations.sandbox.SandboxClient"),
        patch("fleetent.session.manager.start_session_maintenance") as session_maint,
    ):
        await agent_app._start_infra(_agent_without_mcp())  # must not raise

    session_maint.assert_called_once()
