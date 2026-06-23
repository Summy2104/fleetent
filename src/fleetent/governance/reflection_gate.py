"""Governance gate for reflection proposal approval and resolve workflows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Literal, cast

from fleetent import observability
from fleetent.reflection import reflection as reflection_api
from fleetent.reflection import store
from fleetent.reflection.reflection import (
    AutoMaintenancePolicy,
    MemoryProposal,
    SkillProposal,
)

_AUTO_APPLY_ACTIONS = frozenset({"mark_stale"})

DecisionInput = Literal[
    "approve",
    "approved",
    "reject",
    "rejected",
    "expire",
    "expired",
    "apply",
    "applied",
]


DecisionState = Literal["approve", "reject", "expire", "apply"]


def _default_agent_memory_reviewer(
    proposal: MemoryProposal,
    actor_user_id: str | None,
) -> str:
    return actor_user_id or proposal.user_id


_agent_memory_reviewer: Callable[[MemoryProposal, str | None], str] = _default_agent_memory_reviewer
# Legacy alias — tests and callers that still use set_shared_memory_reviewer
_shared_memory_reviewer = _agent_memory_reviewer


def set_agent_memory_reviewer(
    reviewer: Callable[[MemoryProposal, str | None], str],
) -> None:
    """Inject a resolver for agent-memory reviewer identity."""
    global _agent_memory_reviewer, _shared_memory_reviewer
    _agent_memory_reviewer = reviewer
    _shared_memory_reviewer = reviewer


def set_shared_memory_reviewer(
    reviewer: Callable[[MemoryProposal, str | None], str],
) -> None:
    """Legacy alias for set_agent_memory_reviewer."""
    set_agent_memory_reviewer(reviewer)


def _decision(decision: DecisionInput) -> DecisionState:
    value = str(decision).strip().lower()
    if value in {"approve", "approved"}:
        return "approve"
    if value in {"reject", "rejected"}:
        return "reject"
    if value in {"expire", "expired"}:
        return "expire"
    if value in {"apply", "applied"}:
        return "apply"
    raise ValueError(f"unknown decision: {decision}")


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _load_memory_proposal(proposal_id: str) -> MemoryProposal:
    proposal = store._get_maintenance_proposal(proposal_id)
    if proposal is None:
        raise ValueError("memory maintenance proposal does not exist")
    return proposal


def _load_skill_proposal(proposal_id: str) -> SkillProposal:
    proposal = store._get_skill_proposal(proposal_id)
    if proposal is None:
        raise ValueError("skill proposal does not exist")
    return proposal


def _load_proposal_type(
    proposal_id: str,
) -> tuple[Literal["memory", "skill"], MemoryProposal | SkillProposal]:
    memory_proposal = store._get_maintenance_proposal(proposal_id)
    if memory_proposal is not None:
        return "memory", memory_proposal

    skill_proposal = store._get_skill_proposal(proposal_id)
    if skill_proposal is not None:
        return "skill", skill_proposal

    raise ValueError(f"proposal {proposal_id} does not exist")


async def resolve_reflection_proposal_action(
    proposal_id: str,
    *,
    decision: DecisionInput,
    actor_user_id: str | None = None,
    reviewer_user_id: str | None = None,
    auto_policy: AutoMaintenancePolicy | None = None,
) -> MemoryProposal | SkillProposal:
    """Resolve one reflection proposal through governance gate handlers."""
    use_public_reflection_api = getattr(reflection_api, "_state_db", None) is not None
    kind, proposal = _load_proposal_type(proposal_id)
    normalized = _decision(decision)

    if kind == "memory":
        memory_proposal = cast(MemoryProposal, proposal)
        actor = actor_user_id if actor_user_id is not None else memory_proposal.user_id

        if normalized == "approve":
            if use_public_reflection_api:
                approved_memory = reflection_api.approve_memory_maintenance_proposal(
                    memory_proposal.id,
                    actor_user_id=actor,
                )
                return await reflection_api.apply_memory_maintenance_proposal(
                    approved_memory.id,
                    actor_user_id=actor,
                    auto_policy=auto_policy,
                )
            approved_memory = approve_memory_maintenance_proposal(
                memory_proposal.id,
                actor_user_id=actor,
            )
            return await apply_memory_maintenance_proposal(
                approved_memory.id,
                actor_user_id=actor,
                auto_policy=auto_policy,
                proposal=approved_memory,
            )

        if normalized == "reject":
            reason = f"proposal {proposal_id} rejected via reflection gate"
            if use_public_reflection_api:
                return reflection_api.reject_memory_maintenance_proposal(
                    memory_proposal.id,
                    actor_user_id=actor,
                )
            return reject_memory_maintenance_proposal(
                memory_proposal.id,
                actor_user_id=actor,
                reason=reason,
            )

        if normalized == "expire":
            if use_public_reflection_api:
                return reflection_api.expire_memory_maintenance_proposal(memory_proposal.id)
            return expire_memory_maintenance_proposal(memory_proposal.id)

        if normalized == "apply":
            if use_public_reflection_api:
                return await reflection_api.apply_memory_maintenance_proposal(
                    memory_proposal.id,
                    actor_user_id=actor,
                    auto_policy=auto_policy,
                )
            return await apply_memory_maintenance_proposal(
                memory_proposal.id,
                actor_user_id=actor,
                auto_policy=auto_policy,
                proposal=memory_proposal,
            )
        raise ValueError(f"unsupported decision: {decision}")

    skill_proposal = cast(SkillProposal, proposal)
    reviewer = reviewer_user_id or actor_user_id

    if normalized == "approve":
        if reviewer is None:
            raise ValueError("reviewer_user_id is required")
        if use_public_reflection_api:
            approved_skill = reflection_api.approve_skill_proposal(
                skill_proposal.id,
                reviewer_user_id=reviewer,
            )
            return await reflection_api.apply_skill_proposal(
                approved_skill.id,
                actor_user_id=reviewer,
            )
        approved_skill = approve_skill_proposal(
            skill_proposal.id,
            reviewer_user_id=reviewer,
        )
        return await apply_skill_proposal(
            approved_skill.id,
            actor_user_id=reviewer,
            proposal=approved_skill,
        )

    if normalized == "reject":
        if reviewer is None:
            raise ValueError("reviewer_user_id is required")
        if use_public_reflection_api:
            return reflection_api.reject_skill_proposal(
                skill_proposal.id,
                reviewer_user_id=reviewer,
                reason=f"proposal {proposal_id} rejected via reflection gate",
            )
        return reject_skill_proposal(
            skill_proposal.id,
            reviewer_user_id=reviewer,
            reason=f"proposal {proposal_id} rejected via reflection gate",
        )

    if normalized == "expire":
        if reviewer is None:
            raise ValueError("reviewer_user_id is required")
        if use_public_reflection_api:
            return expire_skill_proposal(
                skill_proposal.id,
                reviewer_user_id=reviewer,
            )
        return expire_skill_proposal(
            skill_proposal.id,
            reviewer_user_id=reviewer,
        )

    if normalized == "apply":
        if actor_user_id is not None:
            actor = actor_user_id
        elif reviewer_user_id is not None:
            actor = reviewer_user_id
        else:
            raise ValueError("actor_user_id is required")
        if use_public_reflection_api:
            return await reflection_api.apply_skill_proposal(
                skill_proposal.id,
                actor_user_id=actor,
            )
        return await apply_skill_proposal(
            skill_proposal.id,
            actor_user_id=actor,
        )

    raise ValueError(f"unsupported decision: {decision}")


async def resolve(
    proposal_id: str,
    *,
    decision: DecisionInput,
    actor_user_id: str | None = None,
    reviewer_user_id: str | None = None,
    auto_policy: AutoMaintenancePolicy | None = None,
) -> MemoryProposal | SkillProposal:
    return await resolve_reflection_proposal_action(
        proposal_id,
        decision=decision,
        actor_user_id=actor_user_id,
        reviewer_user_id=reviewer_user_id,
        auto_policy=auto_policy,
    )


def approve_skill_proposal(
    proposal_id: str,
    *,
    reviewer_user_id: str,
) -> SkillProposal:
    proposal = _load_skill_proposal(proposal_id)
    _require_skill_proposal_status(proposal, {"pending"})
    now = _now()
    updated = _replace_skill_proposal(
        proposal,
        status="approved",
        reviewer_user_id=reviewer_user_id,
        reviewed_at=now,
        updated_at=now,
    )
    store._update_skill_proposal(updated)
    return updated


def reject_skill_proposal(
    proposal_id: str,
    *,
    reviewer_user_id: str,
    reason: str,
) -> SkillProposal:
    proposal = _load_skill_proposal(proposal_id)
    _require_skill_proposal_status(proposal, {"pending", "approved"})
    now = _now()
    updated = _replace_skill_proposal(
        proposal,
        status="rejected",
        reviewer_user_id=reviewer_user_id,
        rejection_reason=reason,
        reviewed_at=now,
        updated_at=now,
    )
    store._update_skill_proposal(updated)
    return updated


def expire_skill_proposal(
    proposal_id: str,
    *,
    reviewer_user_id: str,
) -> SkillProposal:
    proposal = _load_skill_proposal(proposal_id)
    _require_skill_proposal_status(proposal, {"pending", "approved"})
    now = _now()
    updated = _replace_skill_proposal(
        proposal,
        status="expired",
        reviewer_user_id=reviewer_user_id,
        reviewed_at=now,
        updated_at=now,
    )
    store._update_skill_proposal(updated)
    return updated


async def apply_skill_proposal(
    proposal_id: str,
    *,
    actor_user_id: str,
    proposal: SkillProposal | None = None,
) -> SkillProposal:
    proposal = proposal if proposal is not None else _load_skill_proposal(proposal_id)
    _require_skill_proposal_status(proposal, {"approved"})
    await apply_skill_proposal_to_boundary(proposal)
    now = _now()
    updated = _replace_skill_proposal(
        proposal,
        status="applied",
        actor_user_id=actor_user_id,
        applied_at=now,
        updated_at=now,
    )
    store._update_skill_proposal(updated)
    return updated


async def apply_skill_proposal_to_boundary(proposal: SkillProposal) -> None:
    await reflection_api.apply_skill_proposal_to_boundary(proposal)


def approve_memory_maintenance_proposal(
    proposal_id: str,
    *,
    actor_user_id: str,
) -> MemoryProposal:
    proposal = _load_memory_proposal(proposal_id)
    _require_owner(proposal, actor_user_id)
    _require_status(proposal, {"pending"})
    updated = _with_status(proposal, "approved")
    store._update_maintenance_proposal(updated)
    _record_maintenance_event("memory_maintenance_proposal_approved", updated)
    return updated


def reject_memory_maintenance_proposal(
    proposal_id: str,
    *,
    actor_user_id: str,
    reason: str | None = None,
) -> MemoryProposal:
    proposal = _load_memory_proposal(proposal_id)
    _require_owner(proposal, actor_user_id)
    _require_status(proposal, {"pending"})
    now = _now()
    updated = _replace_memory_proposal(
        proposal,
        status="rejected",
        reviewed_at=now,
        updated_at=now,
    )
    if reason is not None:
        updated = _replace_memory_proposal(
            updated,
            metadata_patch={**updated.metadata_patch, **{"rejection_reason": reason}},
        )
    store._update_maintenance_proposal(updated)
    _record_maintenance_event("memory_maintenance_proposal_rejected", updated)
    return updated


def expire_memory_maintenance_proposal(
    proposal_id: str,
) -> MemoryProposal:
    proposal = _load_memory_proposal(proposal_id)
    _require_status(proposal, {"pending", "approved"})
    updated = _with_status(proposal, "expired")
    store._update_maintenance_proposal(updated)
    return updated


def mark_agent_memory_proposal_applied(proposal_id: str) -> MemoryProposal:
    proposal = _load_memory_proposal(proposal_id)
    _require_status(proposal, {"approved"})
    if proposal.action != "suggest_agent_memory_or_kb":
        raise ValueError("proposal is not an agent memory suggestion")
    if proposal.metadata_patch.get("target") != "agent_memory":
        raise ValueError("proposal target is not agent_memory")
    updated = _with_status(proposal, "applied")
    store._update_maintenance_proposal(updated)
    _record_maintenance_event("agent_memory_proposal_applied", updated)
    return updated


async def apply_memory_maintenance_proposal(
    proposal_id: str,
    *,
    actor_user_id: str | None = None,
    auto_policy: AutoMaintenancePolicy | None = None,
    proposal: MemoryProposal | None = None,
) -> MemoryProposal:
    proposal = proposal if proposal is not None else _load_memory_proposal(proposal_id)
    if _is_expired(proposal):
        proposal = _with_status(proposal, "expired")
        store._update_maintenance_proposal(proposal)

    if proposal.status in {"rejected", "expired", "applied"}:
        raise ValueError(f"cannot apply {proposal.status} proposal")

    auto_allowed = _auto_apply_allowed(proposal, auto_policy)
    if not auto_allowed:
        if actor_user_id is None:
            raise PermissionError("owner approval is required")
        _require_owner(proposal, actor_user_id)
        _require_status(proposal, {"approved"})

    await _apply_maintenance_action(
        proposal,
        actor_user_id=actor_user_id or proposal.user_id,
    )
    updated = _with_status(proposal, "applied")
    store._update_maintenance_proposal(updated)
    _record_maintenance_event("memory_maintenance_proposal_applied", updated)
    return updated


async def _apply_maintenance_action(
    proposal: MemoryProposal,
    *,
    actor_user_id: str | None = None,
) -> None:
    if proposal.action == "mark_stale":
        from fleetent import memory

        for memory_id in proposal.target_memory_ids:
            await memory.mark_user_memory_stale(proposal.user_id, memory_id)
        return

    if proposal.action in {"rewrite", "compact"}:
        content = _require_proposed_content(proposal)
        if not proposal.target_memory_ids:
            raise ValueError("target_memory_ids must not be empty")
        from fleetent import memory

        await memory.update_user_memory_content(
            proposal.user_id,
            proposal.target_memory_ids[0],
            content,
        )
        return

    if proposal.action == "merge":
        from fleetent import memory

        await memory.merge_user_memories(
            proposal.user_id,
            proposal.target_memory_ids,
            _require_proposed_content(proposal),
        )
        return

    if proposal.action == "delete":
        from fleetent import memory

        for memory_id in proposal.target_memory_ids:
            await memory.delete_user_memory(proposal.user_id, memory_id)
        return

    if proposal.action in ("suggest_agent_memory_or_kb", "suggest_shared_memory_or_kb"):
        target = proposal.metadata_patch.get("target")
        if target in ("agent_memory", "shared_memory"):
            actor = _agent_memory_reviewer(
                proposal,
                actor_user_id or proposal.user_id,
            )
            from fleetent.memory import agent_memory as agent_memory_module

            await agent_memory_module.apply_agent_memory_proposal(
                proposal.id,
                actor_id=actor,
            )
            return
        if target == "knowledge_base":
            raise RuntimeError("knowledge base proposals are no longer handled on the agent side")
        raise ValueError("proposal target is not agent_memory")

    raise ValueError(f"unsupported maintenance action: {proposal.action}")


def _auto_apply_allowed(
    proposal: MemoryProposal,
    auto_policy: AutoMaintenancePolicy | None,
) -> bool:
    return (
        auto_policy is not None
        and auto_policy.allow_low_risk
        and proposal.risk == "low"
        and proposal.action in _AUTO_APPLY_ACTIONS
    )


def _require_owner(proposal: MemoryProposal, actor_user_id: str) -> None:
    if actor_user_id != proposal.user_id:
        raise PermissionError("User Memory owner is required")


def _require_status(
    proposal: MemoryProposal,
    allowed: set[str],
) -> None:
    if proposal.status not in allowed:
        raise ValueError(f"cannot use {proposal.status} proposal")


def _require_skill_proposal_status(
    proposal: SkillProposal,
    allowed: set[str],
) -> None:
    if proposal.status not in allowed:
        expected = ", ".join(sorted(allowed))
        raise ValueError(f"skill proposal must be {expected}, got {proposal.status}")


def _with_status(
    proposal: MemoryProposal,
    status: str,
) -> MemoryProposal:
    return _replace_memory_proposal(
        proposal,
        status=status,
        updated_at=_now(),
    )


def _replace_memory_proposal(
    proposal: MemoryProposal,
    **changes: object,
) -> MemoryProposal:
    data = asdict(proposal)
    data.update(changes)
    return MemoryProposal(**data)


def _replace_skill_proposal(
    proposal: SkillProposal,
    **changes: object,
) -> SkillProposal:
    data = asdict(proposal)
    data.update(changes)
    return SkillProposal(**data)


def _is_expired(proposal: MemoryProposal) -> bool:
    if proposal.expires_at is None:
        return False
    return proposal.expires_at < _now()


def _require_proposed_content(proposal: MemoryProposal) -> str:
    if proposal.proposed_content is None or not proposal.proposed_content.strip():
        raise ValueError("proposed_content is required")
    return proposal.proposed_content.strip()


def _record_maintenance_event(event_type: str, proposal: MemoryProposal) -> None:
    observability.record_trace_event(
        observability.TraceEvent(
            run_id=proposal.id,
            event_type=event_type,
            payload={
                "proposal_id": proposal.id,
                "action": proposal.action,
                "risk": proposal.risk,
                "status": proposal.status,
            },
            user_id=proposal.user_id,
        )
    )
