"""Persistence helpers for memory maintenance proposals used in memory domain."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from fleetent.governance import approval_request_store
from fleetent.memory import store

MaintenanceAction = Literal[
    "mark_stale",
    "merge",
    "rewrite",
    "compact",
    "delete",
    "suggest_shared_memory_or_kb",
]
MaintenanceRisk = Literal["low", "medium", "high"]
MaintenanceStatus = Literal["pending", "approved", "rejected", "applied", "expired"]


@dataclass(frozen=True)
class MemoryMaintenanceProposal:
    """Read model of a proposal row from the shared reflection table."""

    id: str
    user_id: str
    action: MaintenanceAction
    target_memory_ids: list[str]
    proposed_content: str | None
    metadata_patch: dict[str, str]
    risk: MaintenanceRisk
    reason: str
    evidence_ids: list[str]
    status: MaintenanceStatus
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    report_id: str | None = None


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"expected datetime, got {type(value).__name__}")


def _parse_optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _parse_datetime(value)


def _to_dict(row: dict[str, Any]) -> MemoryMaintenanceProposal:
    payload = json.loads(str(row["payload_json"]))
    return MemoryMaintenanceProposal(
        id=str(row["id"]),
        user_id=str(row["subject_user_id"]),
        action=cast(MaintenanceAction, row["kind"]),
        target_memory_ids=[str(value) for value in payload.get("target_memory_ids", [])],
        proposed_content=(
            str(payload["proposed_content"])
            if payload.get("proposed_content") is not None
            else None
        ),
        metadata_patch={
            str(key): str(value) for key, value in dict(payload.get("metadata_patch", {})).items()
        },
        risk=cast(MaintenanceRisk, row["risk"]),
        reason=str(row["reason"]),
        evidence_ids=[str(value) for value in json.loads(str(row["evidence_json"]))],
        status=cast(MaintenanceStatus, _proposal_status_for_row(row)),
        created_at=_parse_datetime(row["created_at"]),
        updated_at=_parse_datetime(row["updated_at"]),
        expires_at=_approval_request_datetime(row["id"], "expires_at"),
        report_id=cast(str | None, row["report_id"]),
    )


def get_memory_maintenance_proposal(proposal_id: str) -> MemoryMaintenanceProposal:
    """Load one User Memory maintenance proposal by id."""
    row = (
        store.database()
        .execute(
            """
            SELECT *
            FROM reflection_proposals
            WHERE id = :id AND domain = 'memory'
            """,
            {"id": proposal_id},
        )
        .fetchone()
    )
    if row is None:
        raise ValueError("memory maintenance proposal does not exist")
    return _to_dict(row)


def list_memory_maintenance_proposals(
    user_id: str,
    start_ts: datetime | None = None,
    *,
    status: MaintenanceStatus | None = None,
) -> list[MemoryMaintenanceProposal]:
    """List User Memory maintenance proposals for one owner."""
    clauses = ["domain = 'memory'", "subject_user_id = :user_id"]
    params: dict[str, object] = {"user_id": user_id}
    if start_ts is not None:
        clauses.append("updated_at >= :start_ts")
        params["start_ts"] = store.format_datetime(start_ts)
    query = f"""
            SELECT *
            FROM reflection_proposals
            WHERE {" AND ".join(clauses)}
            ORDER BY updated_at DESC, id ASC
            """
    try:
        rows = (
            store.database()
            .execute(
                query,
                params,
            )
            .fetchall()
        )
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise
    proposals = [_to_dict(row) for row in rows]
    if status is None:
        return proposals
    return [proposal for proposal in proposals if proposal.status == status]


def mark_shared_memory_proposal_applied(proposal_id: str) -> MemoryMaintenanceProposal:
    """Mark one shared-memory-style proposal as applied and return the projection."""
    proposal = get_memory_maintenance_proposal(proposal_id)
    if proposal.status != "approved":
        raise ValueError(f"cannot mark {proposal.status} proposal")
    if proposal.action != "suggest_shared_memory_or_kb":
        raise ValueError("proposal is not a shared memory suggestion")
    if proposal.metadata_patch.get("target") != "shared_memory":
        raise ValueError("proposal target is not shared_memory")
    now = datetime.now(UTC).replace(microsecond=0)
    updated = MemoryMaintenanceProposal(
        id=proposal.id,
        user_id=proposal.user_id,
        action=proposal.action,
        target_memory_ids=proposal.target_memory_ids,
        proposed_content=proposal.proposed_content,
        metadata_patch=proposal.metadata_patch,
        risk=proposal.risk,
        reason=proposal.reason,
        evidence_ids=proposal.evidence_ids,
        status="applied",
        created_at=proposal.created_at,
        updated_at=now,
        expires_at=proposal.expires_at,
        report_id=proposal.report_id,
    )
    store.database().execute(
        """
        UPDATE reflection_proposals
        SET updated_at = :updated_at,
            payload_json = :payload_json,
            evidence_json = :evidence_json,
            risk = :risk,
            reason = :reason,
            actor_user_id = :actor_user_id,
            applied_at = :applied_at
        WHERE id = :id
        """,
        {
            "id": updated.id,
            "updated_at": store.format_datetime(updated.updated_at),
            "payload_json": json.dumps(
                {
                    "target_memory_ids": updated.target_memory_ids,
                    "proposed_content": updated.proposed_content,
                    "metadata_patch": updated.metadata_patch,
                },
                sort_keys=True,
            ),
            "evidence_json": json.dumps(updated.evidence_ids, sort_keys=True),
            "risk": updated.risk,
            "reason": updated.reason,
            "actor_user_id": None,
            "applied_at": store.format_datetime(updated.updated_at),
        },
    )
    return updated


def _approval_request_row(proposal_id: object) -> dict[str, Any] | None:
    try:
        approval_request_store.set_state_db(store.database())
        return approval_request_store.get_request(str(proposal_id))
    except RuntimeError:
        return None


def _approval_request_value(proposal_id: object, key: str) -> str | None:
    row = _approval_request_row(proposal_id)
    if row is None:
        return None
    value = row.get(key)
    return str(value) if value is not None else None


def _approval_request_datetime(proposal_id: object, key: str) -> datetime | None:
    return _parse_optional_datetime(_approval_request_value(proposal_id, key))


def _proposal_status_for_row(row: dict[str, Any]) -> str:
    if row.get("applied_at") is not None:
        return "applied"
    request = _approval_request_row(row["id"])
    if request is None:
        return "pending"
    return str(request["status"])
