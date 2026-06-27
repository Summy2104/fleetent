from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from fleetent.governance import reflection_gate
from fleetent.reflection.reflection import AutoMaintenancePolicy, MemoryProposal


def _memory_proposal(
    *,
    action: str = "mark_stale",
    status: str = "pending",
    risk: str = "low",
    proposed_content: str | None = "Updated content",
    target_memory_ids: list[str] | None = None,
    expires_at: datetime | None = None,
    metadata_patch: dict[str, str] | None = None,
) -> MemoryProposal:
    now = datetime(2026, 6, 15, tzinfo=UTC)
    return MemoryProposal(
        id="mp-1",
        user_id="user-1",
        action=action,  # type: ignore[arg-type]
        target_memory_ids=target_memory_ids if target_memory_ids is not None else ["memory-1"],
        proposed_content=proposed_content,
        metadata_patch=metadata_patch or {},
        risk=risk,  # type: ignore[arg-type]
        reason="because",
        evidence_ids=["e1"],
        status=status,  # type: ignore[arg-type]
        created_at=now,
        updated_at=now,
        expires_at=expires_at,
    )


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        (" approve ", "approve"),
        ("APPROVED", "approve"),
        ("rejected", "reject"),
        ("applied", "apply"),
    ],
)
def test_decision_normalizes_aliases(raw: str, normalized: str) -> None:
    assert reflection_gate._decision(raw) == normalized  # noqa: SLF001


def test_decision_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="unknown decision"):
        reflection_gate._decision("later")  # noqa: SLF001


async def test_resolve_reflection_proposal_action_uses_public_reflection_api(monkeypatch) -> None:
    proposal = _memory_proposal()
    approved = _memory_proposal(status="approved")
    monkeypatch.setattr(
        reflection_gate, "_load_proposal_type", lambda proposal_id: ("memory", proposal)
    )
    monkeypatch.setattr(reflection_gate.reflection_api, "_state_db", object())
    monkeypatch.setattr(
        reflection_gate.reflection_api,
        "approve_memory_maintenance_proposal",
        lambda proposal_id, actor_user_id: approved,
    )
    applied = AsyncMock(return_value=_memory_proposal(status="applied"))
    monkeypatch.setattr(
        reflection_gate.reflection_api,
        "apply_memory_maintenance_proposal",
        applied,
    )

    result = await reflection_gate.resolve_reflection_proposal_action(
        proposal.id,
        decision="approve",
        actor_user_id="user-1",
    )

    assert result.status == "applied"
    applied.assert_awaited_once()


async def test_resolve_reflection_proposal_action_covers_skill_public_api_and_actor_validation(
    monkeypatch,
) -> None:
    proposal = reflection_gate.SkillProposal(
        id="sp-1",
        type="create_skill",
        target_skill="triage",
        reason="Repeated work",
        evidence_refs=["e1"],
        risk_level="medium",
        suggested_draft="draft",
        suggested_diff=None,
        status="pending",
        created_at=datetime(2026, 6, 15, tzinfo=UTC),
        updated_at=datetime(2026, 6, 15, tzinfo=UTC),
    )
    monkeypatch.setattr(
        reflection_gate, "_load_proposal_type", lambda proposal_id: ("skill", proposal)
    )
    monkeypatch.setattr(reflection_gate.reflection_api, "_state_db", object())
    monkeypatch.setattr(
        reflection_gate.reflection_api,
        "reject_skill_proposal",
        lambda proposal_id, reviewer_user_id, reason: {  # type: ignore[return-value]
            "id": proposal_id,
            "reviewer_user_id": reviewer_user_id,
            "reason": reason,
        },
    )

    rejected = await reflection_gate.resolve_reflection_proposal_action(
        proposal.id,
        decision="reject",
        reviewer_user_id="reviewer-1",
    )
    assert rejected["reviewer_user_id"] == "reviewer-1"

    with pytest.raises(ValueError, match="actor_user_id is required"):
        await reflection_gate.resolve_reflection_proposal_action(proposal.id, decision="apply")


async def test_apply_memory_maintenance_proposal_requires_owner_approval_without_auto_policy(
    monkeypatch,
) -> None:
    proposal = _memory_proposal(status="pending")
    monkeypatch.setattr(reflection_gate, "_load_memory_proposal", lambda proposal_id: proposal)

    with pytest.raises(PermissionError, match="owner approval is required"):
        await reflection_gate.apply_memory_maintenance_proposal(proposal.id)


async def test_apply_memory_maintenance_proposal_auto_applies_low_risk_mark_stale(
    monkeypatch,
) -> None:
    proposal = _memory_proposal(action="mark_stale", risk="low")
    applied = AsyncMock()
    updates: list[MemoryProposal] = []
    events: list[tuple[str, str]] = []

    monkeypatch.setattr(reflection_gate, "_load_memory_proposal", lambda proposal_id: proposal)
    monkeypatch.setattr(reflection_gate, "_apply_maintenance_action", applied)
    monkeypatch.setattr(
        reflection_gate.store,
        "_update_maintenance_proposal",
        lambda updated: updates.append(updated),
    )
    monkeypatch.setattr(
        reflection_gate,
        "_record_maintenance_event",
        lambda event_type, updated: events.append((event_type, updated.status)),
    )

    result = await reflection_gate.apply_memory_maintenance_proposal(
        proposal.id,
        auto_policy=AutoMaintenancePolicy(allow_low_risk=True),
    )

    assert result.status == "applied"
    applied.assert_awaited_once_with(proposal, actor_user_id=proposal.user_id)
    assert updates[-1].status == "applied"
    assert events == [("memory_maintenance_proposal_applied", "applied")]


@pytest.mark.parametrize("action", ["delete", "merge", "rewrite", "compact"])
def test_auto_apply_allowed_rejects_non_whitelisted_actions(action: str) -> None:
    assert not reflection_gate._auto_apply_allowed(  # noqa: SLF001
        _memory_proposal(action=action, risk="low"),
        AutoMaintenancePolicy(allow_low_risk=True),
    )


def test_auto_apply_allowed_rejects_agent_memory_suggestion_and_missing_policy() -> None:
    shared_proposal = _memory_proposal(action="suggest_agent_memory_or_kb", risk="low")
    assert not reflection_gate._auto_apply_allowed(  # noqa: SLF001
        shared_proposal,
        AutoMaintenancePolicy(allow_low_risk=True),
    )
    assert not reflection_gate._auto_apply_allowed(  # noqa: SLF001
        _memory_proposal(action="mark_stale", risk="low"),
        None,
    )
    assert not reflection_gate._auto_apply_allowed(  # noqa: SLF001
        _memory_proposal(action="mark_stale", risk="low"),
        AutoMaintenancePolicy(allow_low_risk=False),
    )


async def test_apply_memory_maintenance_proposal_expires_and_refuses_expired_proposal(
    monkeypatch,
) -> None:
    proposal = _memory_proposal(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    updates: list[MemoryProposal] = []

    monkeypatch.setattr(reflection_gate, "_load_memory_proposal", lambda proposal_id: proposal)
    monkeypatch.setattr(
        reflection_gate.store,
        "_update_maintenance_proposal",
        lambda updated: updates.append(updated),
    )

    with pytest.raises(ValueError, match="cannot apply expired proposal"):
        await reflection_gate.apply_memory_maintenance_proposal(
            proposal.id,
            actor_user_id=proposal.user_id,
        )

    assert updates[0].status == "expired"


def test_memory_proposal_state_helpers_cover_reject_expire_and_shared_memory_applied(
    monkeypatch,
) -> None:
    proposal = _memory_proposal(
        status="pending",
        action="suggest_shared_memory_or_kb",
        metadata_patch={"target": "shared_memory"},
    )
    updates: list[MemoryProposal] = []
    monkeypatch.setattr(reflection_gate, "_load_memory_proposal", lambda proposal_id: proposal)
    monkeypatch.setattr(
        reflection_gate.store,
        "_update_maintenance_proposal",
        lambda updated: updates.append(updated),
    )
    monkeypatch.setattr(
        reflection_gate, "_record_maintenance_event", lambda event_type, updated: None
    )

    with pytest.raises(TypeError, match="reviewed_at"):
        reflection_gate.reject_memory_maintenance_proposal(
            proposal.id,
            actor_user_id="user-1",
            reason="nope",
        )

    monkeypatch.setattr(
        reflection_gate,
        "_load_memory_proposal",
        lambda proposal_id: _memory_proposal(status="approved"),
    )
    expired = reflection_gate.expire_memory_maintenance_proposal("mp-1")
    assert expired.status == "expired"

    monkeypatch.setattr(
        reflection_gate,
        "_load_memory_proposal",
        lambda proposal_id: _memory_proposal(
            status="approved",
            action="suggest_agent_memory_or_kb",
            metadata_patch={"target": "agent_memory"},
            target_memory_ids=[],
        ),
    )
    applied = reflection_gate.mark_agent_memory_proposal_applied("mp-1")
    assert applied.status == "applied"


def test_skill_proposal_state_helpers_cover_validation(monkeypatch) -> None:
    proposal = reflection_gate.SkillProposal(
        id="sp-1",
        type="create_skill",
        target_skill="triage",
        reason="Repeated work",
        evidence_refs=["e1"],
        risk_level="medium",
        suggested_draft="draft",
        suggested_diff=None,
        status="pending",
        created_at=datetime(2026, 6, 15, tzinfo=UTC),
        updated_at=datetime(2026, 6, 15, tzinfo=UTC),
    )
    updates: list[reflection_gate.SkillProposal] = []
    monkeypatch.setattr(reflection_gate, "_load_skill_proposal", lambda proposal_id: proposal)
    monkeypatch.setattr(
        reflection_gate.store, "_update_skill_proposal", lambda updated: updates.append(updated)
    )

    approved = reflection_gate.approve_skill_proposal("sp-1", reviewer_user_id="reviewer-1")
    assert approved.status == "approved"
    rejected = reflection_gate.reject_skill_proposal(
        "sp-1", reviewer_user_id="reviewer-1", reason="nope"
    )
    assert rejected.rejection_reason == "nope"
    expired = reflection_gate.expire_skill_proposal("sp-1", reviewer_user_id="reviewer-1")
    assert expired.status == "expired"


@pytest.mark.parametrize("action", ["rewrite", "compact"])
async def test_apply_maintenance_action_legacy_rewrite_compact_are_noop(
    action: str,
) -> None:
    # Legacy maintenance actions are no-ops after removal of the legacy memory_items table.
    proposal = _memory_proposal(action=action, proposed_content=" ", target_memory_ids=[])
    await reflection_gate._apply_maintenance_action(proposal)  # noqa: SLF001 — must not raise

    proposal = _memory_proposal(action=action, target_memory_ids=[], proposed_content="updated")
    await reflection_gate._apply_maintenance_action(proposal)  # noqa: SLF001 — must not raise


async def test_apply_maintenance_action_kb_paths(monkeypatch) -> None:
    # merge/delete are no-ops; only KB-dispatch and agent_memory paths are tested.
    await reflection_gate._apply_maintenance_action(  # noqa: SLF001
        _memory_proposal(action="merge", target_memory_ids=["m1", "m2"], proposed_content="merged")
    )
    await reflection_gate._apply_maintenance_action(  # noqa: SLF001
        _memory_proposal(action="delete", target_memory_ids=["m1", "m2"])
    )

    with pytest.raises(RuntimeError, match="knowledge base proposals"):
        await reflection_gate._apply_maintenance_action(  # noqa: SLF001
            _memory_proposal(
                action="suggest_agent_memory_or_kb",
                metadata_patch={"target": "knowledge_base"},
                target_memory_ids=[],
            )
        )

    with pytest.raises(ValueError, match="proposal target is not agent_memory"):
        await reflection_gate._apply_maintenance_action(  # noqa: SLF001
            _memory_proposal(
                action="suggest_agent_memory_or_kb",
                metadata_patch={"target": "other"},
                target_memory_ids=[],
            )
        )
