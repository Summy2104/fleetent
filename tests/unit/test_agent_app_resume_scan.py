"""Unit tests: agent_app._start_infra triggers agent-side resume scan at startup."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _fake_agent() -> MagicMock:
    agent = MagicMock()
    agent.mcp_servers = []
    return agent


_NOOP_INIT_SCHEMA = patch(
    "fleetent.runtime.agent_app._init_agent_db_schema",
    MagicMock(),
)
_NOOP_RECONCILE = patch(
    "fleetent.runtime.approval_resume.reconcile_expired_approvals",
    AsyncMock(return_value=0),
)


async def test_start_infra_calls_agent_side_resume_scan(tmp_path: Path) -> None:
    import fleetent.runtime.agent_app as app_mod

    with (
        _NOOP_INIT_SCHEMA,
        _NOOP_RECONCILE,
        patch("fleetent.integrations.sandbox.enablement.get_effective_mode", AsyncMock()),
        patch("fleetent.session.manager.start_session_maintenance"),
        patch("fleetent.session.manager.scan_and_mark_recent_resume") as mock_scan,
    ):
        mock_scan.return_value = []
        await app_mod._start_infra(_fake_agent(), tmp_path / "data")

    mock_scan.assert_called_once()


async def test_start_infra_resume_scan_failure_does_not_abort(tmp_path: Path) -> None:
    import fleetent.runtime.agent_app as app_mod

    with (
        _NOOP_INIT_SCHEMA,
        _NOOP_RECONCILE,
        patch("fleetent.integrations.sandbox.enablement.get_effective_mode", AsyncMock()),
        patch("fleetent.session.manager.start_session_maintenance"),
        patch(
            "fleetent.session.manager.scan_and_mark_recent_resume",
            side_effect=RuntimeError("scan boom"),
        ),
    ):
        await app_mod._start_infra(_fake_agent(), tmp_path / "data")  # must not raise


def test_agent_app_does_not_import_platform_session_admin_store() -> None:
    """Decoupling guard: agent_app must not reference platform session_admin_store."""
    import pathlib

    src = pathlib.Path("src/fleetent/runtime/agent_app.py").read_text()
    assert "session_admin_store" not in src
    assert "platform.chat_management" not in src
