from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from fleetent.governance import reflection_gate
from fleetent.reflection.reflection import AutoMaintenancePolicy, MemoryMaintenanceProposal


def _memory_proposal(
    *,
    action: str = "mark_stale",
    status: str = "pending",
    risk: str = "low",
    proposed_content: str | None = "Updated content",
    target_memory_ids: list[str] | None = None,
    expires_at: datetime | None = None,
    metadata_patch: dict[str, str] | None = None,
) -> MemoryMaintenanceProposal:
    now = datetime(2026, 6, 15, tzinfo=UTC)
    return MemoryMaintenanceProposal(
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
    [(" approve ", "approve"), ("APPROVED", "approve"), ("rejected", "reject"), ("applied", "apply")],
)
def test_decision_normalizes_aliases(raw: str, normalized: str) -> None:
    assert reflection_gate._decision(raw) == normalized  # noqa: SLF001


def test_decision_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="unknown decision"):
        reflection_gate._decision("later")  # noqa: SLF001


async def test_apply_memory_maintenance_proposal_requires_owner_approval_without_auto_policy(
    monkeypatch,
) -> None:
    proposal = _memory_proposal(status="pending")
    monkeypatch.setattr(reflection_gate, "_load_memory_proposal", lambda proposal_id: proposal)

    with pytest.raises(PermissionError, match="owner approval is required"):
        await reflection_gate.apply_memory_maintenance_proposal(proposal.id)


async def test_apply_memory_maintenance_proposal_auto_applies_low_risk_mark_stale(monkeypatch) -> None:
    proposal = _memory_proposal(action="mark_stale", risk="low")
    applied = AsyncMock()
    updates: list[MemoryMaintenanceProposal] = []
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


async def test_apply_memory_maintenance_proposal_expires_and_refuses_expired_proposal(monkeypatch) -> None:
    proposal = _memory_proposal(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    updates: list[MemoryMaintenanceProposal] = []

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


@pytest.mark.parametrize("action", ["rewrite", "compact"])
async def test_apply_maintenance_action_requires_content_and_target_for_rewrite_like_actions(
    monkeypatch,
    action: str,
) -> None:
    proposal = _memory_proposal(action=action, proposed_content=" ", target_memory_ids=[])

    with pytest.raises(ValueError, match="proposed_content is required"):
        await reflection_gate._apply_maintenance_action(proposal)  # noqa: SLF001

    proposal = _memory_proposal(action=action, target_memory_ids=[], proposed_content="updated")
    with pytest.raises(ValueError, match="target_memory_ids must not be empty"):
        await reflection_gate._apply_maintenance_action(proposal)  # noqa: SLF001


async def test_apply_maintenance_action_merge_delete_and_kb_paths(monkeypatch) -> None:
    merge = AsyncMock()
    delete = AsyncMock()
    monkeypatch.setattr("fleetent.memory.merge_user_memories", merge)
    monkeypatch.setattr("fleetent.memory.delete_user_memory", delete)

    await reflection_gate._apply_maintenance_action(  # noqa: SLF001
        _memory_proposal(action="merge", target_memory_ids=["m1", "m2"], proposed_content="merged")
    )
    merge.assert_awaited_once_with("user-1", ["m1", "m2"], "merged")

    await reflection_gate._apply_maintenance_action(  # noqa: SLF001
        _memory_proposal(action="delete", target_memory_ids=["m1", "m2"])
    )
    assert delete.await_count == 2

    with pytest.raises(RuntimeError, match="knowledge base proposals"):
        await reflection_gate._apply_maintenance_action(  # noqa: SLF001
            _memory_proposal(
                action="suggest_shared_memory_or_kb",
                metadata_patch={"target": "knowledge_base"},
                target_memory_ids=[],
            )
        )

    with pytest.raises(ValueError, match="proposal target is not shared_memory"):
        await reflection_gate._apply_maintenance_action(  # noqa: SLF001
            _memory_proposal(
                action="suggest_shared_memory_or_kb",
                metadata_patch={"target": "other"},
                target_memory_ids=[],
            )
        )
