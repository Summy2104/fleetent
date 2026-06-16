"""resources_from_agent_settings: build SandboxResources from a per-agent
SandboxResourcesSettings, reusing the value-level validation/clamp/enum-fallback
that the (removed) platform.yaml path used (per-agent-sandbox-resources).
"""

from __future__ import annotations

from unittest.mock import patch

from fleetent.agent_config import SandboxResourcesSettings
from fleetent.integrations.sandbox.config import (
    NetworkPolicy,
    SandboxResources,
    resources_from_agent_settings,
)


def test_all_unset_equals_code_defaults() -> None:
    assert resources_from_agent_settings(SandboxResourcesSettings()) == SandboxResources()


def test_declared_fields_override() -> None:
    r = resources_from_agent_settings(
        SandboxResourcesSettings(
            memory=512, cpus=1.0, network="public_only", read_only=False, cap_add=["NET_ADMIN"]
        )
    )
    assert r.memory == 512
    assert r.cpus == 1.0
    assert r.network is NetworkPolicy.PUBLIC_ONLY
    assert r.read_only is False
    assert r.cap_add == ("NET_ADMIN",)
    # Unset fields keep code defaults.
    assert r.exec_timeout == SandboxResources().exec_timeout
    assert r.pids_limit == SandboxResources().pids_limit


def test_invalid_values_fall_back_with_warning() -> None:
    with patch("fleetent.integrations.sandbox.config._logger") as log:
        r = resources_from_agent_settings(
            SandboxResourcesSettings(memory=0, network="bogus", pids_limit=-1)
        )
    d = SandboxResources()
    assert r.memory == d.memory  # 0 invalid → default
    assert r.network == d.network  # unknown enum → default (none)
    assert r.pids_limit == d.pids_limit  # negative → default
    log.warn.assert_called()


def test_exec_timeout_clamped() -> None:
    assert resources_from_agent_settings(SandboxResourcesSettings(exec_timeout=0)).exec_timeout == 1
    assert (
        resources_from_agent_settings(SandboxResourcesSettings(exec_timeout=1000)).exec_timeout
        == 600
    )
