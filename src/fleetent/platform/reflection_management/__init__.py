"""Reflection management platform APIs.

Thin platform-side shell over the agent's reflection store. The capability
itself — the self-evolution engine, the approval gate, and proposal/report
storage — stays agent-side under ``fleetent.reflection`` / ``fleetent.governance``.
This module is read-only: it exposes listing, diff viewing, and trend queries to
the platform console, but approval and application stay in the agent-owned DM
workflow.
"""

from typing import Any

from fleetent.reflection import (
    ReflectionTrendQuery,
    ReflectionTrendSummary,
    get_reflection_trend_summary,
    get_skill_proposal,
    list_skill_proposals,
    state_db_initialized,
)
from fleetent.structured_logging import get_logger

_logger = get_logger("reflection_management")

__all__ = [
    "ReflectionTrendQuery",
    "ReflectionTrendSummary",
    "get_reflection_trend_summary",
    "get_skill_proposal",
    "list_skill_proposals",
    "reflection_list_proposals",
    "reflection_proposal_diff",
]


def _proposal_dict(p: Any) -> dict[str, Any]:
    """Serialize a reflection SkillProposal to a JSON-able review-inbox row."""
    return {
        "id": p.id,
        "report_id": p.report_id,
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
    """Pending Skill proposals from the agent reflection store (newest first).

    Reflection proposals live in each agent's per-agent state DB, wired only inside the agent
    process. The platform control plane injects no state DB, so degrade to an empty inbox rather
    than surfacing ``_database``'s boot-time RuntimeError as a 500.
    """
    if not state_db_initialized():
        _logger.warn("reflection_proposals_unavailable_no_state_db")
        return []
    return [_proposal_dict(p) for p in list_skill_proposals("pending")]


def reflection_proposal_diff(proposal_id: str) -> dict[str, Any]:
    """Full proposal payload incl. suggested diff/draft, for the review viewer."""
    if not state_db_initialized():
        _logger.warn("reflection_proposal_diff_unavailable_no_state_db")
        return {"proposal_id": proposal_id, "diff": "", "draft": ""}
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
