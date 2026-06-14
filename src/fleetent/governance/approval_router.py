"""Unified approval router keyed by approval_request subject_type."""

from __future__ import annotations

from typing import Literal

from fleetent.governance import approval_request_store, approval_store, reflection_gate
from fleetent.governance.permission_gate import _default_gate


async def _resolve_tool_call(
    *,
    approval_id: str,
    decision: Literal["approved", "rejected"],
    approver_user_id: str,
    always: bool,
    authorized_actors: set[str] | None,
) -> bool:
    return await _default_gate.resolve_tool_call_approval(
        approval_id=approval_id,
        decision=decision,
        approver_user_id=approver_user_id,
        always=always,
        authorized_actors=authorized_actors,
    )


async def _resolve_reflection_proposal(
    *,
    approval_id: str,
    decision: Literal["approved", "rejected"],
    approver_user_id: str,
) -> bool:
    await reflection_gate.resolve_reflection_proposal_action(
        approval_id,
        decision=decision,
        actor_user_id=approver_user_id,
        reviewer_user_id=approver_user_id,
    )
    return True


async def resolve_approval_request(
    *,
    approval_id: str,
    decision: Literal["approved", "rejected"],
    approver_user_id: str,
    always: bool = False,
    authorized_actors: set[str] | None = None,
) -> bool:
    row = approval_request_store.get_request(approval_id)
    if row is None:
        try:
            legacy = approval_store.get_approval(approval_id)
        except Exception:  # noqa: BLE001 - compatibility fallback must stay best-effort
            legacy = None
        if legacy is None:
            return False
        return await _resolve_tool_call(
            approval_id=approval_id,
            decision=decision,
            approver_user_id=approver_user_id,
            always=always,
            authorized_actors=authorized_actors,
        )

    subject_type = str(row["subject_type"])
    if subject_type == "tool_call":
        return await _resolve_tool_call(
            approval_id=approval_id,
            decision=decision,
            approver_user_id=approver_user_id,
            always=always,
            authorized_actors=authorized_actors,
        )
    if subject_type in {"memory_proposal", "skill_proposal"}:
        return await _resolve_reflection_proposal(
            approval_id=approval_id,
            decision=decision,
            approver_user_id=approver_user_id,
        )
    raise ValueError(f"unknown approval subject_type: {subject_type}")
