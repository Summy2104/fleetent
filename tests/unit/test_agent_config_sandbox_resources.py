"""Per-agent sandbox resources/lifecycle schema on agent.yaml SandboxSettings
(per-agent-sandbox-resources). Resources/hardening/lifecycle move off the
machine-shared platform.yaml onto each agent's SandboxSettings.resources.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fleetent.agent_config import AgentFile, default_models


def _agent(sandbox: dict) -> AgentFile:
    return AgentFile(name="a", version=1, models=default_models(), sandbox=sandbox)


def test_resources_block_parsed() -> None:
    af = _agent(
        {
            "resources": {
                "network": "public_only",
                "memory": 512,
                "cpus": 1.0,
                "read_only": False,
                "exec_timeout": 60,
                "memory_swap_mb": 1024,
                "pids_limit": 128,
                "tmpfs_size_mb": 32,
                "cap_drop_all": False,
                "cap_add": ["NET_ADMIN"],
                "no_new_privileges": False,
                "init": False,
                "run_as_user": "0:0",
            },
            "workspace_scope": "agent",
            "idle_hours": 4.0,
        }
    )
    r = af.sandbox.resources
    assert r.network == "public_only"
    assert r.memory == 512
    assert r.cpus == 1.0
    assert r.read_only is False
    assert r.exec_timeout == 60
    assert r.memory_swap_mb == 1024
    assert r.pids_limit == 128
    assert r.tmpfs_size_mb == 32
    assert r.cap_drop_all is False
    assert r.cap_add == ["NET_ADMIN"]
    assert r.no_new_privileges is False
    assert r.init is False
    assert r.run_as_user == "0:0"
    assert af.sandbox.workspace_scope == "agent"
    assert af.sandbox.idle_hours == 4.0


def test_resources_defaults_unset() -> None:
    af = AgentFile(name="a", version=1, models=default_models())
    # Unset → all fields None (built against code defaults later), lifecycle None.
    r = af.sandbox.resources
    assert r.network is None and r.memory is None and r.cpus is None
    assert r.read_only is None and r.exec_timeout is None
    assert af.sandbox.workspace_scope is None
    assert af.sandbox.idle_hours is None


def test_partial_resources_only_declared_fields() -> None:
    af = _agent({"resources": {"network": "none"}})
    assert af.sandbox.resources.network == "none"
    assert af.sandbox.resources.memory is None


def test_unknown_sandbox_key_still_rejected() -> None:
    # extra="forbid" preserved: an unknown sandbox key is rejected.
    with pytest.raises(ValidationError):
        _agent({"resources": {"network": "none"}, "bogus_key": 1})


def test_unknown_resources_key_rejected() -> None:
    with pytest.raises(ValidationError):
        _agent({"resources": {"not_a_field": 1}})
