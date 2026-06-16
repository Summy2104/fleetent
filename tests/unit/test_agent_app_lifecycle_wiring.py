"""_start_infra wires sandbox orphan-cleanup + idle-sweep into agent runtime boot.

All collaborators are mocked (no real Docker / asyncio tasks / MCP), keeping this
single-module behavioural test at unit level.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fleetent.integrations.sandbox import Mode
from fleetent.runtime import agent_app


def _agent_without_mcp() -> MagicMock:
    agent = MagicMock()
    agent.mcp_servers = []
    return agent


_NOOP_INIT_SCHEMA = patch(
    "fleetent.runtime.agent_app._init_agent_db_schema",
    MagicMock(),
)

# _start_infra now reconciles this agent's expired approvals (#8) right after
# _init_agent_db_schema wires approval_store's state_db. These tests NOOP that wiring,
# so they must stub reconcile too — it would otherwise find no state_db and raise.
_NOOP_RECONCILE = patch(
    "fleetent.runtime.approval_resume.reconcile_expired_approvals",
    AsyncMock(),
)


async def test_start_infra_cleans_orphans_and_starts_sweep_when_docker_available(
    tmp_path: Path,
) -> None:
    with (
        _NOOP_INIT_SCHEMA,
        _NOOP_RECONCILE,
        patch(
            "fleetent.integrations.sandbox.enablement.get_effective_mode",
            AsyncMock(return_value=Mode.ALL),
        ),
        patch("fleetent.integrations.sandbox.cleanup_orphans", AsyncMock()) as cleanup,
        patch("fleetent.integrations.sandbox.start_idle_sweep") as sweep,
        patch("fleetent.integrations.sandbox.SandboxClient"),
        patch("fleetent.session.manager.start_session_maintenance"),
    ):
        await agent_app._start_infra(_agent_without_mcp(), tmp_path / "data")

    cleanup.assert_awaited_once()
    sweep.assert_called_once()


async def test_start_infra_skips_sandbox_lifecycle_when_docker_unavailable(
    tmp_path: Path,
) -> None:
    with (
        _NOOP_INIT_SCHEMA,
        _NOOP_RECONCILE,
        patch(
            "fleetent.integrations.sandbox.enablement.get_effective_mode",
            AsyncMock(return_value=Mode.OFF),
        ),
        patch("fleetent.integrations.sandbox.cleanup_orphans", AsyncMock()) as cleanup,
        patch("fleetent.integrations.sandbox.start_idle_sweep") as sweep,
        patch("fleetent.session.manager.start_session_maintenance"),
    ):
        await agent_app._start_infra(_agent_without_mcp(), tmp_path / "data")

    cleanup.assert_not_awaited()
    sweep.assert_not_called()


async def test_start_infra_inits_sandbox_manager_with_per_agent_skills_root(
    tmp_path: Path,
) -> None:
    """The sandbox manager is (re)built with the agent-selected backend AND the
    per-agent skills root (== the scan root) as the mount source default, so the
    container's /workspace/skills matches what the skill index was scanned from
    (sandbox-skill-mount-per-agent-root)."""
    with (
        _NOOP_INIT_SCHEMA,
        _NOOP_RECONCILE,
        patch(
            "fleetent.integrations.sandbox.enablement.get_effective_mode",
            AsyncMock(return_value=Mode.ALL),
        ),
        patch("fleetent.integrations.sandbox.cleanup_orphans", AsyncMock()),
        patch("fleetent.integrations.sandbox.start_idle_sweep"),
        patch("fleetent.tools.builtin_tools.init_sandbox_manager") as init_mgr,
        patch("fleetent.session.manager.start_session_maintenance"),
    ):
        agent = _agent_without_mcp()
        await agent_app._start_infra(agent, tmp_path / "data")

    init_mgr.assert_called_once_with(agent, agent_skills_root=tmp_path / "skills")


async def test_start_infra_cleanup_failure_does_not_block_startup(tmp_path: Path) -> None:
    """An orphan-cleanup error is logged; boot still proceeds to session maintenance."""
    with (
        _NOOP_INIT_SCHEMA,
        _NOOP_RECONCILE,
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
        await agent_app._start_infra(_agent_without_mcp(), tmp_path / "data")  # must not raise

    session_maint.assert_called_once()
