"""Unit tests for AgentFile.approval routing block (A2).

Tests ApprovalRouting schema parsing, defaults, and extra="forbid" behavior.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


# ── ApprovalEntry parsing ──────────────────────────────────────────────────────


def test_approval_entry_defaults() -> None:
    """ApprovalEntry: default policy is 'any', approvers defaults to empty list."""
    from fleetent.agent_config import ApprovalEntry

    entry = ApprovalEntry()
    assert entry.approvers == []
    assert entry.policy == "any"


def test_approval_entry_parses_approvers_and_policy() -> None:
    from fleetent.agent_config import ApprovalEntry

    entry = ApprovalEntry(approvers=["slack:U123", "telegram:456"], policy="all")
    assert entry.approvers == ["slack:U123", "telegram:456"]
    assert entry.policy == "all"


def test_approval_entry_rejects_extra_fields() -> None:
    from fleetent.agent_config import ApprovalEntry

    with pytest.raises(ValidationError):
        ApprovalEntry(approvers=[], unknown_field="bad")  # type: ignore[call-arg]


# ── ApprovalRouting parsing ────────────────────────────────────────────────────


def test_approval_routing_defaults() -> None:
    """ApprovalRouting: on_no_approver defaults to 'reject', by_risk and by_tool are empty."""
    from fleetent.agent_config import ApprovalRouting

    routing = ApprovalRouting()
    assert routing.on_no_approver == "reject"
    assert routing.by_risk.medium is None
    assert routing.by_risk.high is None
    assert routing.by_tool == {}


def test_approval_routing_parses_by_risk() -> None:
    from fleetent.agent_config import ApprovalRouting

    routing = ApprovalRouting(
        by_risk={
            "medium": {"approvers": ["slack:U_MED"], "policy": "any"},
            "high": {"approvers": ["slack:U_HIGH", "telegram:999"], "policy": "all"},
        }
    )
    assert routing.by_risk.medium is not None
    assert routing.by_risk.medium.approvers == ["slack:U_MED"]
    assert routing.by_risk.medium.policy == "any"
    assert routing.by_risk.high is not None
    assert routing.by_risk.high.approvers == ["slack:U_HIGH", "telegram:999"]
    assert routing.by_risk.high.policy == "all"


def test_approval_routing_parses_by_tool() -> None:
    from fleetent.agent_config import ApprovalRouting

    routing = ApprovalRouting(
        by_tool={
            "delete_prod_db": {"approvers": ["slack:U_OPS"], "policy": "any"},
        }
    )
    assert "delete_prod_db" in routing.by_tool
    assert routing.by_tool["delete_prod_db"].approvers == ["slack:U_OPS"]


def test_approval_routing_rejects_extra_fields() -> None:
    from fleetent.agent_config import ApprovalRouting

    with pytest.raises(ValidationError):
        ApprovalRouting(on_no_approver="reject", bad_field="bad")  # type: ignore[call-arg]


# ── AgentFile.approval integration ────────────────────────────────────────────


def test_agent_file_approval_is_none_by_default() -> None:
    """AgentFile without an approval block: .approval is None."""
    from fleetent.agent_config import AgentFile, default_models

    agent = AgentFile(name="test-agent", version=1, models=default_models())
    assert agent.approval is None


def test_agent_file_parses_approval_block() -> None:
    """AgentFile with a full approval block: parsed correctly."""
    from fleetent.agent_config import AgentFile, default_models

    agent = AgentFile(
        name="test-agent",
        version=1,
        models=default_models(),
        approval={
            "on_no_approver": "reject",
            "by_risk": {
                "high": {"approvers": ["slack:U_LEAD"], "policy": "any"},
            },
            "by_tool": {
                "run_code": {"approvers": ["slack:U_SEC"], "policy": "all"},
            },
        },
    )
    assert agent.approval is not None
    assert agent.approval.on_no_approver == "reject"
    assert agent.approval.by_risk.high is not None
    assert agent.approval.by_risk.high.approvers == ["slack:U_LEAD"]
    assert "run_code" in agent.approval.by_tool
