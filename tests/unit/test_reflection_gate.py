from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from fleetent.governance import reflection_gate
from fleetent.reflection import store
from fleetent.reflection.reflection import MemoryMaintenanceProposal, SkillProposal


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)


def _memory_proposal(
    *,
    id: str = "mp-1",
    user_id: str = "user-1",
    action: str = "mark_stale",
    metadata_patch: dict[str, str] | None = None,
    target_memory_ids: list[str] | None = None,
) -> MemoryMaintenanceProposal:
    return MemoryMaintenanceProposal(
        id=id,
        user_id=user_id,
        action=action,
        target_memory_ids=target_memory_ids or ["memory-1"],
        proposed_content="Team uses Scrum for weekly demos.",
        metadata_patch=metadata_patch or {},
        risk="low",
        reason="repeatable memory signal",
        evidence_ids=["e1", "e2"],
        status="pending",
        created_at=_now(),
        updated_at=_now(),
        expires_at=None,
    )


def _skill_proposal(
    *,
    id: str = "sp-1",
    status: str = "pending",
) -> SkillProposal:
    return SkillProposal(
        id=id,
        type="create_skill",
        target_skill="triage-alerts",
        reason="Recurring pattern detected.",
        evidence_refs=["e1", "e2"],
        risk_level="medium",
        suggested_draft=None,
        suggested_diff="",
        status=status,
        created_at=_now(),
        updated_at=_now(),
        reviewer_user_id=None,
        reviewed_at=None,
        rejection_reason=None,
        actor_user_id=None,
        applied_at=None,
    )


async def test_resolve_approve_user_memory_proposal_calls_memory_boundary(
    monkeypatch,
) -> None:
    proposal = _memory_proposal()
    updates: list[MemoryMaintenanceProposal] = []
    mark_user_memory_stale = AsyncMock()

    monkeypatch.setattr(store, "_get_maintenance_proposal", lambda _id: proposal)
    monkeypatch.setattr(store, "_get_skill_proposal", lambda _id: None)
    monkeypatch.setattr(store, "_update_maintenance_proposal", updates.append)
    monkeypatch.setattr(
        reflection_gate,
        "_record_maintenance_event",
        lambda _event_type, _proposal: None,
    )
    from fleetent import memory as memory_module

    monkeypatch.setattr(
        memory_module,
        "mark_user_memory_stale",
        mark_user_memory_stale,
    )

    result = await reflection_gate.resolve(
        proposal.id,
        decision="approve",
        actor_user_id=proposal.user_id,
    )

    assert result.status == "applied"
    mark_user_memory_stale.assert_awaited_once_with(
        proposal.user_id,
        proposal.target_memory_ids[0],
    )
    assert [proposal.status for proposal in updates] == ["approved", "applied"]


async def test_resolve_expire_skill_proposal_sets_expired_state(
    monkeypatch,
) -> None:
    proposal = _skill_proposal()
    updates: list[SkillProposal] = []

    monkeypatch.setattr(store, "_get_maintenance_proposal", lambda _id: None)
    monkeypatch.setattr(store, "_get_skill_proposal", lambda _id: proposal)
    monkeypatch.setattr(store, "_update_skill_proposal", updates.append)

    result = await reflection_gate.resolve(
        proposal.id,
        decision="expired",
        reviewer_user_id="reviewer-1",
    )

    assert isinstance(result, SkillProposal)
    assert result.status == "expired"
    assert updates and updates[-1].status == "expired"


async def test_resolve_approve_shared_memory_proposal_calls_shared_memory_boundary(
    monkeypatch,
) -> None:
    proposal = _memory_proposal(
        id="mp-shared",
        action="suggest_shared_memory_or_kb",
        metadata_patch={"target": "shared_memory"},
        target_memory_ids=[],
    )
    updates: list[MemoryMaintenanceProposal] = []
    apply_shared_memory_proposal = AsyncMock()

    monkeypatch.setattr(store, "_get_maintenance_proposal", lambda _id: proposal)
    monkeypatch.setattr(store, "_get_skill_proposal", lambda _id: None)
    monkeypatch.setattr(store, "_update_maintenance_proposal", updates.append)
    monkeypatch.setattr(
        reflection_gate,
        "_record_maintenance_event",
        lambda _event_type, _proposal: None,
    )
    from fleetent.memory import shared as shared_memory

    monkeypatch.setattr(
        shared_memory,
        "apply_shared_memory_proposal",
        apply_shared_memory_proposal,
    )

    result = await reflection_gate.resolve(
        proposal.id,
        decision="approved",
        actor_user_id=proposal.user_id,
    )

    assert result.status == "applied"
    apply_shared_memory_proposal.assert_awaited_once_with(
        proposal.id,
        actor_id=proposal.user_id,
    )
    assert [proposal.status for proposal in updates] == ["approved", "applied"]


async def test_shared_memory_reviewer_resolver_is_injected(monkeypatch) -> None:
    proposal = _memory_proposal(
        id="mp-shared-review",
        action="suggest_shared_memory_or_kb",
        metadata_patch={"target": "shared_memory"},
        target_memory_ids=[],
    )
    updates: list[MemoryMaintenanceProposal] = []
    apply_shared_memory_proposal = AsyncMock()

    monkeypatch.setattr(store, "_get_maintenance_proposal", lambda _id: proposal)
    monkeypatch.setattr(store, "_get_skill_proposal", lambda _id: None)
    monkeypatch.setattr(store, "_update_maintenance_proposal", updates.append)
    monkeypatch.setattr(
        reflection_gate,
        "_record_maintenance_event",
        lambda _event_type, _proposal: None,
    )
    from fleetent.memory import shared as shared_memory

    monkeypatch.setattr(
        shared_memory,
        "apply_shared_memory_proposal",
        apply_shared_memory_proposal,
    )
    original_reviewer = reflection_gate._shared_memory_reviewer

    try:
        reflection_gate.set_shared_memory_reviewer(
            lambda _proposal, actor_id: "resolved-reviewer",
        )

        await reflection_gate.resolve(
            proposal.id,
            decision="approved",
            actor_user_id=proposal.user_id,
        )
    finally:
        reflection_gate.set_shared_memory_reviewer(original_reviewer)

    apply_shared_memory_proposal.assert_awaited_once_with(
        proposal.id,
        actor_id="resolved-reviewer",
    )


async def test_resolve_approve_skill_proposal_calls_skill_boundary(
    monkeypatch,
) -> None:
    proposal = _skill_proposal()
    updates: list[SkillProposal] = []
    apply_boundary = AsyncMock()

    monkeypatch.setattr(store, "_get_maintenance_proposal", lambda _id: None)
    monkeypatch.setattr(store, "_get_skill_proposal", lambda _id: proposal)
    monkeypatch.setattr(store, "_update_skill_proposal", updates.append)
    monkeypatch.setattr(
        reflection_gate,
        "apply_skill_proposal_to_boundary",
        apply_boundary,
    )

    result = await reflection_gate.resolve(
        proposal.id,
        decision="approved",
        reviewer_user_id="reviewer-1",
    )

    assert isinstance(result, SkillProposal)
    assert result.status == "applied"
    apply_boundary.assert_awaited_once()
    assert apply_boundary.await_args is not None
    (awaited_proposal,) = apply_boundary.await_args.args
    assert awaited_proposal.id == proposal.id
    assert awaited_proposal.status == "approved"
    assert [proposal.status for proposal in updates] == ["approved", "applied"]
