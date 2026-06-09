"""Config-field tests for the Action Gate (action-gate).

GovernanceConfig + AgentFile carry the per-agent medium/high mode policy; defaults keep
the merged approval-routing contract (medium/high → approval).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_governance_config_defaults_to_approval() -> None:
    from fleetent.runtime.snapshot import GovernanceConfig

    cfg = GovernanceConfig()
    assert cfg.action_gate_medium_mode == "approval"
    assert cfg.action_gate_high_mode == "approval"


def test_agent_file_action_gate_defaults() -> None:
    from fleetent.agent_config import AgentFile, default_models

    agent = AgentFile(name="a", version=1, models=default_models())
    assert agent.action_gate_medium_mode == "approval"
    assert agent.action_gate_high_mode == "approval"


def test_agent_file_accepts_valid_modes() -> None:
    from fleetent.agent_config import AgentFile, default_models

    agent = AgentFile(
        name="a",
        version=1,
        models=default_models(),
        action_gate_medium_mode="sandbox",
        action_gate_high_mode="direct",
    )
    assert agent.action_gate_medium_mode == "sandbox"
    assert agent.action_gate_high_mode == "direct"


def test_agent_file_rejects_invalid_mode() -> None:
    from fleetent.agent_config import AgentFile, default_models

    with pytest.raises(ValidationError):
        AgentFile(
            name="a",
            version=1,
            models=default_models(),
            action_gate_medium_mode="reject",  # reject is reserved for CRITICAL only
        )


def test_agent_file_rejects_garbage_mode() -> None:
    from fleetent.agent_config import AgentFile, default_models

    with pytest.raises(ValidationError):
        AgentFile(
            name="a",
            version=1,
            models=default_models(),
            action_gate_high_mode="nonsense",
        )


def test_governance_from_file_passes_through() -> None:
    from fleetent.agent_config import AgentFile, default_models
    from fleetent.runtime.snapshot import _governance_from_file

    agent = AgentFile(
        name="a",
        version=1,
        models=default_models(),
        action_gate_medium_mode="sandbox",
        action_gate_high_mode="approval",
    )
    cfg = _governance_from_file(agent)
    assert cfg.action_gate_medium_mode == "sandbox"
    assert cfg.action_gate_high_mode == "approval"
