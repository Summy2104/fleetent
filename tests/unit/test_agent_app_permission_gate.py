"""Unit tests verifying agent_app reads permission_gate_enabled from AgentFile.

The /chat route uses run_stream (which has no permission gate); this test
verifies the field is accessible on the agent object as part of ensuring
the configuration is wired end-to-end.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest
import yaml


def _write_agent_yaml(home: Path, permission_gate_enabled: bool = True) -> None:
    agent_yaml = {
        "name": home.name,
        "version": 1,
        "models": {
            "targets": [
                {
                    "id": "default",
                    "provider": "local",
                    "protocol": "openai_chat",
                    "base_url": "http://localhost:11434/v1/",
                    "model": "default",
                }
            ],
            "routes": {"default": [{"target": "default"}]},
        },
        "permission_gate_enabled": permission_gate_enabled,
        "permission_gate_medium_timeout_seconds": 60,
        "permission_gate_high_timeout_seconds": 120,
    }
    (home / "agent.yaml").write_text(yaml.dump(agent_yaml))


async def test_agent_permission_gate_enabled_readable_at_boot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """boot() loads an agent with permission_gate_enabled=False without crashing."""
    home = tmp_path / "myagent"
    home.mkdir()
    _write_agent_yaml(home, permission_gate_enabled=False)
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))

    loaded_agent = None

    async def capture_infra(agent):
        nonlocal loaded_agent
        loaded_agent = agent

    with (
        patch("fleetent.runtime.agent_app._start_infra", capture_infra),
        patch("fleetent.skills.scan"),
        patch("fleetent.tools.plugin_loader.load_plugins"),
        patch("fleetent.intelligence.vector_store.configure_from_active_agent"),
        patch("fleetent.observability.structured_logging.configure_structured_logging"),
        patch("structlog.configure"),
    ):
        from fleetent.runtime import agent_app

        sup = MagicMock()
        sup.start = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock()
        sup.stop_all = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock()

        await agent_app.boot(
            "myagent",
            home=home,
            start_im=False,
            with_infra=True,
            supervisor=sup,
            telegram_supervisor=sup,
        )

    assert loaded_agent is not None
    assert loaded_agent.permission_gate_enabled is False
    assert loaded_agent.permission_gate_medium_timeout_seconds == 60
    assert loaded_agent.permission_gate_high_timeout_seconds == 120
