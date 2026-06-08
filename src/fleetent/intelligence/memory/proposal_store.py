"""Persistence helpers for memory maintenance proposals used in memory domain."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from fleetent.intelligence.memory import store

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
    return MemoryMaintenanceProposal(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        action=cast(MaintenanceAction, row["action"]),
        target_memory_ids=[str(value) for value in json.loads(str(row["target_memory_ids_json"]))],
        proposed_content=(
            str(row["proposed_content"]) if row.get("proposed_content") is not None else None
        ),
        metadata_patch={
            str(key): str(value)
            for key, value in json.loads(str(row["metadata_patch_json"])).items()
        },
        risk=cast(MaintenanceRisk, row["risk"]),
        reason=str(row["reason"]),
        evidence_ids=[str(value) for value in json.loads(str(row["evidence_ids_json"]))],
        status=cast(MaintenanceStatus, row["status"]),
        created_at=_parse_datetime(row["created_at"]),
        updated_at=_parse_datetime(row["updated_at"]),
        expires_at=_parse_optional_datetime(row.get("expires_at")),
    )


def _has_table() -> bool:
    return (
        store.database()
        .execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'memory_maintenance_proposals'
            """,
            {},
        )
        .fetchone()
        is not None
    )


def get_memory_maintenance_proposal(proposal_id: str) -> MemoryMaintenanceProposal:
    """Load one User Memory maintenance proposal by id."""
    row = (
        store.database()
        .execute(
            """
            SELECT *
            FROM memory_maintenance_proposals
            WHERE id = :id
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
    *,
    status: MaintenanceStatus | None = None,
) -> list[MemoryMaintenanceProposal]:
    """List User Memory maintenance proposals for one owner."""
    if not _has_table():
        return []
    clauses = ["user_id = :user_id"]
    params: dict[str, object] = {"user_id": user_id}
    if status is not None:
        clauses.append("status = :status")
        params["status"] = status

    rows = (
        store.database()
        .execute(
            f"""
            SELECT *
            FROM memory_maintenance_proposals
            WHERE {" AND ".join(clauses)}
            ORDER BY updated_at DESC, id ASC
            """,
            params,
        )
        .fetchall()
    )
    return [_to_dict(row) for row in rows]


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
    )
    store.database().execute(
        """
        UPDATE memory_maintenance_proposals
        SET status = :status,
            updated_at = :updated_at,
            target_memory_ids_json = :target_memory_ids_json,
            proposed_content = :proposed_content,
            metadata_patch_json = :metadata_patch_json,
            evidence_ids_json = :evidence_ids_json,
            risk = :risk,
            reason = :reason
        WHERE id = :id
        """,
        {
            "id": updated.id,
            "status": updated.status,
            "updated_at": store.format_datetime(updated.updated_at),
            "target_memory_ids_json": json.dumps(updated.target_memory_ids, sort_keys=True),
            "proposed_content": updated.proposed_content,
            "metadata_patch_json": json.dumps(updated.metadata_patch, sort_keys=True),
            "evidence_ids_json": json.dumps(updated.evidence_ids, sort_keys=True),
            "risk": updated.risk,
            "reason": updated.reason,
        },
    )
    return updated
