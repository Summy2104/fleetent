"""init_sandbox_manager injects per-agent resources/workspace_scope/idle_hours
into SandboxManager (per-agent-sandbox-resources). Two agents with different
sandbox.resources get independent resource profiles; manager no longer falls
back to platform.yaml for resources/lifecycle.
"""

from __future__ import annotations

from fleetent.agent_config import AgentFile, default_models
from fleetent.integrations.sandbox.config import NetworkPolicy
from fleetent.integrations.sandbox.manager import WorkspaceScope
from fleetent.tools.builtin_tools import init_sandbox_manager


def _agent(sandbox: dict) -> AgentFile:
    return AgentFile(name="a", version=1, models=default_models(), sandbox=sandbox)


def test_init_injects_agent_resources() -> None:
    mgr = init_sandbox_manager(
        _agent(
            {
                "resources": {"network": "public_only", "memory": 512},
                "workspace_scope": "agent",
                "idle_hours": 5.0,
                "multi_user": False,
            }
        )
    )
    r = mgr.resources_by_scope[WorkspaceScope.SESSION]
    assert r.network is NetworkPolicy.PUBLIC_ONLY
    assert r.memory == 512
    # Collapsed single tier: AGENT tier == SESSION tier.
    assert mgr.resources_by_scope[WorkspaceScope.AGENT] == r
    # workspace_scope=agent honoured (multi_user False so the guard does not downgrade).
    assert mgr.scope is WorkspaceScope.AGENT
    assert mgr.idle_hours == 5.0


def test_init_defaults_when_resources_unset() -> None:
    mgr = init_sandbox_manager(_agent({}))
    r = mgr.resources_by_scope[WorkspaceScope.SESSION]
    assert r.network is NetworkPolicy.NONE  # code default
    assert r.memory == 256
    assert mgr.scope is WorkspaceScope.SESSION
    assert mgr.idle_hours == 2.0


def test_two_agents_independent_resources() -> None:
    a = init_sandbox_manager(_agent({"resources": {"network": "public_only"}}))
    a_net = a.resources_by_scope[WorkspaceScope.SESSION].network
    b = init_sandbox_manager(_agent({}))  # default none
    b_net = b.resources_by_scope[WorkspaceScope.SESSION].network
    assert a_net is NetworkPolicy.PUBLIC_ONLY
    assert b_net is NetworkPolicy.NONE
