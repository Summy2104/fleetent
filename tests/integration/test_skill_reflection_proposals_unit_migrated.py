import pytest

from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _patch_reflection_db(monkeypatch, tmp_path):
    from fleetent import reflection

    db_path = tmp_path / "skill-proposals.db"
    database = SQLiteDatabase(path=db_path)
    migrate(database, AGENT_STATE_MIGRATIONS)
    monkeypatch.setattr(reflection, "_state_db", database)
    return database


def test_skill_proposal_public_api_is_importable():
    from fleetent.reflection import (
        SkillProposal,
        apply_skill_proposal,
        approve_skill_proposal,
        generate_skill_proposals,
        reject_skill_proposal,
    )

    assert SkillProposal is not None
    assert generate_skill_proposals is not None
    assert approve_skill_proposal is not None
    assert reject_skill_proposal is not None
    assert apply_skill_proposal is not None


def test_generate_skill_proposals_creates_updates_deprecates_and_ignores_noise(
    monkeypatch,
    tmp_path,
):
    _patch_reflection_db(monkeypatch, tmp_path)
    from fleetent.reflection import ReflectionFinding, generate_skill_proposals

    proposals = generate_skill_proposals(
        findings=[
            ReflectionFinding(
                type="skill_opportunity",
                summary="Repeated task pattern may become a skill: summarize Jira progress",
                evidence_ids=["trace-a", "trace-b"],
                metadata={"pattern": "summarize Jira progress"},
            )
        ],
        skill_signals=[
            {
                "skill_name": "incident-runbook",
                "trigger_count": 12,
                "failure_count": 6,
                "reason": "missing rollback step",
            },
            {
                "skill_name": "legacy-summary",
                "trigger_count": 0,
                "days_unused": 120,
                "reason": "no recent usage",
            },
            {
                "skill_name": "healthy-skill",
                "trigger_count": 2,
                "failure_count": 0,
            },
        ],
    )

    assert [proposal.type for proposal in proposals] == [
        "create_skill",
        "update_skill",
        "deprecate_skill",
    ]
    assert proposals[0].status == "pending"
    assert proposals[0].suggested_draft is not None
    assert "summarize-jira-progress" in proposals[0].target_skill
    assert proposals[1].suggested_diff is not None
    assert proposals[2].target_skill == "legacy-summary"


def test_skill_proposal_review_lifecycle(monkeypatch, tmp_path):
    _patch_reflection_db(monkeypatch, tmp_path)
    from fleetent.reflection import (
        ReflectionFinding,
        approve_skill_proposal,
        generate_skill_proposals,
        get_skill_proposal,
        reject_skill_proposal,
    )

    [proposal] = generate_skill_proposals(
        findings=[
            ReflectionFinding(
                type="skill_opportunity",
                summary="Repeated task pattern may become a skill: triage incidents",
                evidence_ids=["trace-a", "trace-b"],
                metadata={"pattern": "triage incidents"},
            )
        ]
    )

    approved = approve_skill_proposal(proposal.id, reviewer_user_id="admin")
    assert approved.status == "approved"
    assert approved.reviewer_user_id == "admin"
    assert approved.reviewed_at is not None

    [rejected] = generate_skill_proposals(
        findings=[
            ReflectionFinding(
                type="skill_opportunity",
                summary="Repeated task pattern may become a skill: draft updates",
                evidence_ids=["trace-c", "trace-d"],
                metadata={"pattern": "draft updates"},
            )
        ]
    )
    rejected = reject_skill_proposal(
        rejected.id,
        reviewer_user_id="admin",
        reason="not useful",
    )
    assert rejected.status == "rejected"
    assert rejected.rejection_reason == "not useful"
    assert get_skill_proposal(rejected.id).status == "rejected"


async def test_apply_skill_proposal_requires_approval_and_uses_boundary(monkeypatch, tmp_path):
    _patch_reflection_db(monkeypatch, tmp_path)
    from fleetent import reflection
    from fleetent.reflection import (
        ReflectionFinding,
        apply_skill_proposal,
        approve_skill_proposal,
        generate_skill_proposals,
        reject_skill_proposal,
    )

    applied: list[tuple[str, str]] = []

    async def apply_boundary(proposal):
        applied.append((proposal.type, proposal.target_skill))

    monkeypatch.setattr(reflection, "apply_skill_proposal_to_boundary", apply_boundary)
    [proposal] = generate_skill_proposals(
        findings=[
            ReflectionFinding(
                type="skill_opportunity",
                summary="Repeated task pattern may become a skill: deploy service",
                evidence_ids=["trace-a", "trace-b"],
                metadata={"pattern": "deploy service"},
            )
        ]
    )

    with pytest.raises(ValueError, match="approved"):
        await apply_skill_proposal(proposal.id, actor_user_id="admin")

    approve_skill_proposal(proposal.id, reviewer_user_id="reviewer")
    applied_proposal = await apply_skill_proposal(proposal.id, actor_user_id="admin")
    assert applied_proposal.status == "applied"
    assert applied_proposal.actor_user_id == "admin"
    assert applied == [("create_skill", "deploy-service")]

    [rejected] = generate_skill_proposals(
        findings=[
            ReflectionFinding(
                type="skill_opportunity",
                summary="Repeated task pattern may become a skill: write one-off note",
                evidence_ids=["trace-x", "trace-y"],
                metadata={"pattern": "write one-off note"},
            )
        ]
    )
    reject_skill_proposal(rejected.id, reviewer_user_id="reviewer", reason="one-off")
    with pytest.raises(ValueError, match="rejected"):
        await apply_skill_proposal(rejected.id, actor_user_id="admin")


def test_real_llm_skill_draft_generation_is_opt_in(monkeypatch):
    from fleetent import reflection

    monkeypatch.delenv("FLEETENT_REFLECTION_REAL_SKILL_DRAFT", raising=False)

    assert reflection._real_skill_draft_enabled() is False
