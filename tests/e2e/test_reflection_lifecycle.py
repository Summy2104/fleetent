from __future__ import annotations

from tests.e2e._reflection_helpers import (
    approve_reflection_proposal_via_im,
    managed_reflection_stack,
    seed_memory_stale_proposal,
    seed_skill_reflection_traces,
    wait_for_memory_proposal_applied,
    wait_for_pending_skill_proposal,
    wait_for_reflection_report,
)


def test_reflection_enabled_managed_agent_emits_scheduler_report() -> None:
    report = wait_for_reflection_report()

    assert report["scope"] == "support"
    assert report["domain"] == "memory"


def test_memory_mark_stale_proposal_can_be_approved_via_im_route() -> None:
    with managed_reflection_stack() as stack:
        seeded = seed_memory_stale_proposal(stack, risk="medium")

        approve_reflection_proposal_via_im(
            stack,
            proposal_id=seeded["proposal_id"],
            user_id=stack.agent_name,
        )
        applied = wait_for_memory_proposal_applied(
            stack,
            proposal_id=seeded["proposal_id"],
            memory_id=seeded["memory_id"],
        )

    assert applied["proposal_status"] == "applied"
    assert applied["memory_status"] == "stale"


def test_reflection_scheduler_generates_pending_skill_proposal_from_repeated_task_pattern() -> None:
    pattern = 'weekly triage workflow'

    with managed_reflection_stack() as stack:
        seed_skill_reflection_traces(stack, pattern=pattern)
        proposal = wait_for_pending_skill_proposal(stack, pattern=pattern)

    assert proposal["domain"] == "skill"
    assert proposal["status"] == "pending"
