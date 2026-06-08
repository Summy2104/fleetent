"""Reflection management platform APIs.

Thin platform-side shell over the agent's reflection store. The capability
itself — the self-evolution engine, the approval gate, and proposal/report
storage — stays agent-side under ``fleetent.reflection`` / ``fleetent.governance``.
This module only *reads* that store to expose listing, the skill-proposal review
surface, and trend queries to the platform console; it holds no capability.
"""

from typing import Any

from fleetent.reflection import (
    ReflectionTrendQuery,
    ReflectionTrendSummary,
    get_reflection_trend_summary,
    get_skill_proposal,
    list_skill_proposals,
)

__all__ = [
    "ReflectionTrendQuery",
    "ReflectionTrendSummary",
    "get_reflection_trend_summary",
    "get_skill_proposal",
    "list_skill_proposals",
    "reflection_list_proposals",
    "reflection_proposal_diff",
    "reflection_apply_proposal",
    "reflection_close_proposal",
]


def _proposal_dict(p: Any) -> dict[str, Any]:
    """Serialize a reflection SkillProposal to a JSON-able review-inbox row."""
    return {
        "id": p.id,
        "type": p.type,
        "target_skill": p.target_skill,
        "reason": p.reason,
        "evidence_refs": list(p.evidence_refs),
        "risk_level": p.risk_level,
        "status": p.status,
        "has_draft": bool(p.suggested_draft),
        "has_diff": bool(p.suggested_diff),
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


def reflection_list_proposals() -> list[dict[str, Any]]:
    """Pending Skill proposals from the agent reflection store (newest first)."""
    return [_proposal_dict(p) for p in list_skill_proposals("pending")]


def reflection_proposal_diff(proposal_id: str) -> dict[str, Any]:
    """Full proposal payload incl. suggested diff/draft, for the review viewer."""
    try:
        p = get_skill_proposal(proposal_id)
    except ValueError:
        return {"proposal_id": proposal_id, "diff": "", "draft": ""}
    return {
        **_proposal_dict(p),
        "proposal_id": p.id,
        "diff": p.suggested_diff or "",
        "draft": p.suggested_draft or "",
    }


def reflection_apply_proposal(proposal_id: str, reviewer_user_id: str) -> None:
    """Approve a Skill proposal (status -> approved)."""
    from fleetent import reflection

    reflection.approve_skill_proposal(proposal_id, reviewer_user_id=reviewer_user_id)


def reflection_close_proposal(
    proposal_id: str, reviewer_user_id: str, reason: str = "rejected via admin console"
) -> None:
    """Reject a Skill proposal without changing the skill."""
    from fleetent import reflection

    reflection.reject_skill_proposal(proposal_id, reviewer_user_id=reviewer_user_id, reason=reason)
