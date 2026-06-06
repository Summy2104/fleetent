"""Unit tests: agent_app._start_infra triggers resume-pending scan at startup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


def _fake_agent():
    agent = MagicMock()
    agent.mcp_servers = []
    return agent


async def test_start_infra_calls_scan_and_mark_recent() -> None:
    import fleetent.runtime.agent_app as app_mod

    with (
        patch("fleetent.integrations.sandbox.enablement.get_effective_mode", AsyncMock()),
        patch("fleetent.session.manager.start_session_maintenance"),
        patch(
            "fleetent.platform.chat_management.session_admin_store.scan_and_mark_recent"
        ) as mock_scan,
    ):
        await app_mod._start_infra(_fake_agent())

    mock_scan.assert_called_once()


async def test_start_infra_resume_scan_failure_does_not_abort() -> None:
    import fleetent.runtime.agent_app as app_mod

    with (
        patch("fleetent.integrations.sandbox.enablement.get_effective_mode", AsyncMock()),
        patch("fleetent.session.manager.start_session_maintenance"),
        patch(
            "fleetent.platform.chat_management.session_admin_store.scan_and_mark_recent",
            side_effect=RuntimeError("db locked"),
        ),
    ):
        # Must not raise despite scan failure
        await app_mod._start_infra(_fake_agent())
