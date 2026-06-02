"""Reflection report public API."""

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

from fleetent import observability
from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.intelligence import memory

FindingType = Literal["memory_candidate", "memory_conflict", "skill_opportunity"]
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

_MUTATING_ACTIONS = {"mark_stale", "merge", "rewrite", "compact", "delete"}


@dataclass(frozen=True)
class ReflectionFinding:
    """A structured reflection suggestion that has not been applied."""

    type: FindingType
    summary: str
    evidence_ids: list[str]
    metadata: dict[str, str]


@dataclass(frozen=True)
class ReflectionReport:
    """A reflection report for one scope and time window."""

    id: str
    scope: str
    time_window: tuple[datetime, datetime]
    findings: list[ReflectionFinding]
    created_at: datetime


@dataclass(frozen=True)
class AutoMaintenancePolicy:
    """Explicit opt-in policy for low-risk User Memory maintenance."""

    allow_low_risk: bool = False


@dataclass(frozen=True)
class MemoryMaintenanceProposal:
    """Owner-approved maintenance proposal for User Memory."""

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
    expires_at: datetime | None


async def run_reflection(scope: str) -> ReflectionReport:
    """Read traces and memory signals, then generate a structured report."""
    now = datetime.now(UTC).replace(microsecond=0)
    start = now - timedelta(days=7)
    events = list(
        observability.query_trace_events(
            observability.TraceQuery(user_id=scope, start_ts=start, end_ts=now)
        )
    )
    memory_signals = await _read_memory_signals(scope, events)
    findings = _generate_findings(events, memory_signals)
    report = ReflectionReport(
        id=str(uuid.uuid4()),
        scope=scope,
        time_window=(start, now),
        findings=findings,
        created_at=now,
    )
    _save_report(report)
    return report


def generate_memory_maintenance_proposals(
    user_id: str,
    findings: list[ReflectionFinding],
) -> list[MemoryMaintenanceProposal]:
    """Generate User Memory maintenance proposals from reflection findings."""
    proposals: list[MemoryMaintenanceProposal] = []
    for finding in findings:
        if finding.type == "memory_candidate":
            fact = finding.metadata.get("fact", "").strip()
            if not fact:
                continue
            if _looks_like_shared_knowledge(fact):
                proposals.append(
                    create_memory_maintenance_proposal(
                        user_id=user_id,
                        action="suggest_shared_memory_or_kb",
                        target_memory_ids=[],
                        proposed_content=fact,
                        risk="low",
                        reason=finding.summary,
                        evidence_ids=finding.evidence_ids,
                        metadata_patch={
                            "boundary": "not_user_memory:suggest_shared_memory_or_kb",
                            "source_finding": finding.type,
                        },
                    )
                )
                continue
            proposals.append(
                create_memory_maintenance_proposal(
                    user_id=user_id,
                    action="rewrite",
                    target_memory_ids=[],
                    proposed_content=fact,
                    risk="medium",
                    reason=finding.summary,
                    evidence_ids=finding.evidence_ids,
                    metadata_patch={
                        "confirmation": "inline",
                        "source_finding": finding.type,
                    },
                )
            )
            continue
        if finding.type == "memory_conflict":
            proposals.append(
                create_memory_maintenance_proposal(
                    user_id=user_id,
                    action="merge",
                    target_memory_ids=finding.evidence_ids,
                    proposed_content=None,
                    risk="medium",
                    reason=finding.summary,
                    evidence_ids=finding.evidence_ids,
                    metadata_patch={
                        "confirmation": "review",
                        "source_finding": finding.type,
                    },
                )
            )
    return proposals


def create_memory_maintenance_proposal(
    *,
    user_id: str,
    action: MaintenanceAction,
    target_memory_ids: list[str],
    proposed_content: str | None,
    risk: MaintenanceRisk,
    reason: str,
    evidence_ids: list[str],
    metadata_patch: dict[str, str] | None = None,
    expires_at: datetime | None = None,
) -> MemoryMaintenanceProposal:
    """Create a pending User Memory maintenance proposal without modifying memory."""
    _validate_proposal_input(user_id, action, risk, target_memory_ids)
    now = datetime.now(UTC).replace(microsecond=0)
    proposal = MemoryMaintenanceProposal(
        id=str(uuid.uuid4()),
        user_id=user_id,
        action=action,
        target_memory_ids=list(target_memory_ids),
        proposed_content=proposed_content.strip() if isinstance(proposed_content, str) else None,
        metadata_patch=dict(metadata_patch or {}),
        risk=risk,
        reason=reason,
        evidence_ids=list(evidence_ids),
        status="pending",
        created_at=now,
        updated_at=now,
        expires_at=expires_at,
    )
    _insert_maintenance_proposal(proposal)
    _record_maintenance_event("memory_maintenance_proposal_created", proposal)
    return proposal


def get_memory_maintenance_proposal(proposal_id: str) -> MemoryMaintenanceProposal:
    """Load one User Memory maintenance proposal by id."""
    proposal = _get_maintenance_proposal(proposal_id)
    if proposal is None:
        raise ValueError("memory maintenance proposal does not exist")
    return proposal


def list_memory_maintenance_proposals(
    user_id: str,
    *,
    status: MaintenanceStatus | None = None,
) -> list[MemoryMaintenanceProposal]:
    """List User Memory maintenance proposals for one owner."""
    clauses = ["user_id = :user_id"]
    params: dict[str, object] = {"user_id": user_id}
    if status is not None:
        clauses.append("status = :status")
        params["status"] = status
    rows = (
        _database()
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
    return [_proposal_from_row(row) for row in rows]


def approve_memory_maintenance_proposal(
    proposal_id: str,
    *,
    actor_user_id: str,
) -> MemoryMaintenanceProposal:
    """Approve a pending proposal as the User Memory owner."""
    proposal = get_memory_maintenance_proposal(proposal_id)
    _require_owner(proposal, actor_user_id)
    _require_status(proposal, {"pending"})
    updated = _with_status(proposal, "approved")
    _update_maintenance_proposal(updated)
    _record_maintenance_event("memory_maintenance_proposal_approved", updated)
    return updated


def reject_memory_maintenance_proposal(
    proposal_id: str,
    *,
    actor_user_id: str,
) -> MemoryMaintenanceProposal:
    """Reject a pending proposal as the User Memory owner."""
    proposal = get_memory_maintenance_proposal(proposal_id)
    _require_owner(proposal, actor_user_id)
    _require_status(proposal, {"pending"})
    updated = _with_status(proposal, "rejected")
    _update_maintenance_proposal(updated)
    _record_maintenance_event("memory_maintenance_proposal_rejected", updated)
    return updated


def expire_memory_maintenance_proposal(proposal_id: str) -> MemoryMaintenanceProposal:
    """Expire a proposal that is no longer actionable."""
    proposal = get_memory_maintenance_proposal(proposal_id)
    _require_status(proposal, {"pending", "approved"})
    updated = _with_status(proposal, "expired")
    _update_maintenance_proposal(updated)
    return updated


async def apply_memory_maintenance_proposal(
    proposal_id: str,
    *,
    actor_user_id: str | None = None,
    auto_policy: AutoMaintenancePolicy | None = None,
) -> MemoryMaintenanceProposal:
    """Apply an approved or explicitly auto-allowed User Memory maintenance proposal."""
    proposal = get_memory_maintenance_proposal(proposal_id)
    if _is_expired(proposal):
        proposal = _with_status(proposal, "expired")
        _update_maintenance_proposal(proposal)
    if proposal.status in {"rejected", "expired", "applied"}:
        raise ValueError(f"cannot apply {proposal.status} proposal")

    auto_allowed = _auto_apply_allowed(proposal, auto_policy)
    if not auto_allowed:
        if actor_user_id is None:
            raise PermissionError("owner approval is required")
        _require_owner(proposal, actor_user_id)
        _require_status(proposal, {"approved"})

    await _apply_maintenance_action(proposal)
    updated = _with_status(proposal, "applied")
    _update_maintenance_proposal(updated)
    _record_maintenance_event("memory_maintenance_proposal_applied", updated)
    return updated


def _save_report(report: ReflectionReport) -> None:
    database = _database()
    if not database.path.exists():
        return
    if not _has_reflection_reports_table(database):
        return
    database.execute(
        """
        INSERT INTO reflection_reports (
            id, scope, time_window_start, time_window_end, findings_json, created_at
        )
        VALUES (
            :id, :scope, :time_window_start, :time_window_end, :findings_json, :created_at
        )
        """,
        {
            "id": report.id,
            "scope": report.scope,
            "time_window_start": report.time_window[0].isoformat(),
            "time_window_end": report.time_window[1].isoformat(),
            "findings_json": _findings_json(report.findings),
            "created_at": report.created_at.isoformat(),
        },
    )


def _database() -> SQLiteDatabase:
    return create_database(Settings(anthropic_api_key="").database_url)


def _has_reflection_reports_table(database: SQLiteDatabase) -> bool:
    row = database.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = :type AND name = :name
        """,
        {"type": "table", "name": "reflection_reports"},
    ).fetchone()
    return row is not None


def _findings_json(findings: list[ReflectionFinding]) -> str:
    payload = [asdict(finding) for finding in findings]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _insert_maintenance_proposal(proposal: MemoryMaintenanceProposal) -> None:
    _database().execute(
        """
        INSERT INTO memory_maintenance_proposals (
            id, user_id, action, target_memory_ids_json, proposed_content,
            metadata_patch_json, risk, reason, evidence_ids_json, status,
            created_at, updated_at, expires_at
        )
        VALUES (
            :id, :user_id, :action, :target_memory_ids_json, :proposed_content,
            :metadata_patch_json, :risk, :reason, :evidence_ids_json, :status,
            :created_at, :updated_at, :expires_at
        )
        """,
        _proposal_params(proposal),
    )


def _update_maintenance_proposal(proposal: MemoryMaintenanceProposal) -> None:
    _database().execute(
        """
        UPDATE memory_maintenance_proposals
        SET status = :status,
            updated_at = :updated_at,
            target_memory_ids_json = :target_memory_ids_json,
            proposed_content = :proposed_content,
            metadata_patch_json = :metadata_patch_json,
            evidence_ids_json = :evidence_ids_json,
            expires_at = :expires_at
        WHERE id = :id
        """,
        _proposal_params(proposal),
    )


def _get_maintenance_proposal(proposal_id: str) -> MemoryMaintenanceProposal | None:
    row = (
        _database()
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
        return None
    return _proposal_from_row(row)


def _proposal_params(proposal: MemoryMaintenanceProposal) -> dict[str, object]:
    return {
        "id": proposal.id,
        "user_id": proposal.user_id,
        "action": proposal.action,
        "target_memory_ids_json": json.dumps(proposal.target_memory_ids, sort_keys=True),
        "proposed_content": proposal.proposed_content,
        "metadata_patch_json": json.dumps(proposal.metadata_patch, sort_keys=True),
        "risk": proposal.risk,
        "reason": proposal.reason,
        "evidence_ids_json": json.dumps(proposal.evidence_ids, sort_keys=True),
        "status": proposal.status,
        "created_at": _format_datetime(proposal.created_at),
        "updated_at": _format_datetime(proposal.updated_at),
        "expires_at": _format_datetime(proposal.expires_at),
    }


def _proposal_from_row(row: dict[str, Any]) -> MemoryMaintenanceProposal:
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


def _with_status(
    proposal: MemoryMaintenanceProposal,
    status: MaintenanceStatus,
) -> MemoryMaintenanceProposal:
    return MemoryMaintenanceProposal(
        id=proposal.id,
        user_id=proposal.user_id,
        action=proposal.action,
        target_memory_ids=proposal.target_memory_ids,
        proposed_content=proposal.proposed_content,
        metadata_patch=proposal.metadata_patch,
        risk=proposal.risk,
        reason=proposal.reason,
        evidence_ids=proposal.evidence_ids,
        status=status,
        created_at=proposal.created_at,
        updated_at=datetime.now(UTC).replace(microsecond=0),
        expires_at=proposal.expires_at,
    )


async def _apply_maintenance_action(proposal: MemoryMaintenanceProposal) -> None:
    if proposal.action == "mark_stale":
        for memory_id in proposal.target_memory_ids:
            await memory.mark_user_memory_stale(proposal.user_id, memory_id)
        return
    if proposal.action in {"rewrite", "compact"}:
        content = _require_proposed_content(proposal)
        if not proposal.target_memory_ids:
            raise ValueError("target_memory_ids must not be empty")
        await memory.update_user_memory_content(
            proposal.user_id,
            proposal.target_memory_ids[0],
            content,
        )
        return
    if proposal.action == "merge":
        await memory.merge_user_memories(
            proposal.user_id,
            proposal.target_memory_ids,
            _require_proposed_content(proposal),
        )
        return
    if proposal.action == "delete":
        for memory_id in proposal.target_memory_ids:
            await memory.delete_user_memory(proposal.user_id, memory_id)
        return
    if proposal.action == "suggest_shared_memory_or_kb":
        return
    raise ValueError(f"unsupported maintenance action: {proposal.action}")


def _auto_apply_allowed(
    proposal: MemoryMaintenanceProposal,
    auto_policy: AutoMaintenancePolicy | None,
) -> bool:
    return (
        auto_policy is not None
        and auto_policy.allow_low_risk
        and proposal.risk == "low"
        and proposal.action not in {"delete", "merge", "rewrite", "compact"}
    )


def _require_owner(proposal: MemoryMaintenanceProposal, actor_user_id: str) -> None:
    if actor_user_id != proposal.user_id:
        raise PermissionError("User Memory owner is required")


def _require_status(
    proposal: MemoryMaintenanceProposal,
    allowed: set[MaintenanceStatus],
) -> None:
    if proposal.status not in allowed:
        raise ValueError(f"cannot use {proposal.status} proposal")


def _require_proposed_content(proposal: MemoryMaintenanceProposal) -> str:
    if proposal.proposed_content is None or not proposal.proposed_content.strip():
        raise ValueError("proposed_content is required")
    return proposal.proposed_content.strip()


def _validate_proposal_input(
    user_id: str,
    action: MaintenanceAction,
    risk: MaintenanceRisk,
    target_memory_ids: list[str],
) -> None:
    if not user_id.strip():
        raise ValueError("user_id must not be empty")
    if action not in {
        "mark_stale",
        "merge",
        "rewrite",
        "compact",
        "delete",
        "suggest_shared_memory_or_kb",
    }:
        raise ValueError(f"unsupported maintenance action: {action}")
    if risk not in {"low", "medium", "high"}:
        raise ValueError(f"unsupported maintenance risk: {risk}")
    if action in _MUTATING_ACTIONS and action != "rewrite" and not target_memory_ids:
        raise ValueError("target_memory_ids must not be empty")


def _is_expired(proposal: MemoryMaintenanceProposal) -> bool:
    if proposal.expires_at is None:
        return False
    return proposal.expires_at < datetime.now(UTC).replace(microsecond=0)


def _record_maintenance_event(event_type: str, proposal: MemoryMaintenanceProposal) -> None:
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


def _looks_like_shared_knowledge(content: str) -> bool:
    normalized = content.casefold()
    markers = (
        "team ",
        "project ",
        "customer ",
        "client ",
        "organization ",
        "company ",
        "团队",
        "项目",
        "客户",
        "组织",
        "公司",
    )
    return any(marker in normalized for marker in markers)


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"expected datetime string, got {type(value).__name__}")


def _parse_optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _parse_datetime(value)


async def _read_memory_signals(
    scope: str, events: list[observability.TraceEvent]
) -> list[memory.MemoryItem]:
    query = _events_to_text(events)
    if not query:
        return []
    return await memory.search(scope, query, limit=10)


def _events_to_text(events: list[observability.TraceEvent]) -> str:
    parts: list[str] = []
    for event in events:
        parts.extend(_text_values(event.payload))
    return "\n".join(parts)


def _text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_text_values(item))
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(_text_values(item))
        return result
    return []


def _generate_findings(
    events: list[observability.TraceEvent], memory_signals: list[memory.MemoryItem]
) -> list[ReflectionFinding]:
    findings: list[ReflectionFinding] = []
    findings.extend(_memory_candidate_findings(events, memory_signals))
    findings.extend(_memory_conflict_findings(memory_signals))
    findings.extend(_skill_opportunity_findings(events))
    return findings


def _memory_candidate_findings(
    events: list[observability.TraceEvent], memory_signals: list[memory.MemoryItem]
) -> list[ReflectionFinding]:
    existing = {item.content.strip().casefold() for item in memory_signals}
    by_fact: dict[str, list[str]] = {}
    for event in events:
        fact = event.payload.get("memory_fact")
        if not isinstance(fact, str) or not fact.strip():
            continue
        normalized = fact.strip()
        by_fact.setdefault(normalized, []).append(_event_evidence_id(event))

    findings: list[ReflectionFinding] = []
    for fact, evidence_ids in by_fact.items():
        if len(evidence_ids) < 2 or fact.casefold() in existing:
            continue
        findings.append(
            ReflectionFinding(
                type="memory_candidate",
                summary=f"Repeated user fact may belong in memory: {fact}",
                evidence_ids=evidence_ids,
                metadata={"fact": fact, "count": str(len(evidence_ids))},
            )
        )
    return findings


def _memory_conflict_findings(
    memory_signals: list[memory.MemoryItem],
) -> list[ReflectionFinding]:
    by_field: dict[str, dict[str, list[memory.MemoryItem]]] = {}
    for item in memory_signals:
        parsed = _parse_memory_field_value(item.content)
        if parsed is None:
            continue
        field, value = parsed
        by_field.setdefault(field, {}).setdefault(value.casefold(), []).append(item)

    findings: list[ReflectionFinding] = []
    for field, values in by_field.items():
        if len(values) < 2:
            continue
        conflicting_items = [items[0] for items in values.values()]
        evidence_ids = [item.id for item in conflicting_items]
        summaries = "; ".join(item.content for item in conflicting_items)
        findings.append(
            ReflectionFinding(
                type="memory_conflict",
                summary=f"Conflicting memory signals for {field}: {summaries}",
                evidence_ids=evidence_ids,
                metadata={"field": field},
            )
        )
    return findings


def _skill_opportunity_findings(events: list[observability.TraceEvent]) -> list[ReflectionFinding]:
    by_pattern: dict[str, list[str]] = {}
    for event in events:
        pattern = event.payload.get("task_pattern")
        if not isinstance(pattern, str) or not pattern.strip():
            continue
        normalized = pattern.strip()
        by_pattern.setdefault(normalized, []).append(_event_evidence_id(event))

    findings: list[ReflectionFinding] = []
    for pattern, evidence_ids in by_pattern.items():
        if len(evidence_ids) < 2:
            continue
        findings.append(
            ReflectionFinding(
                type="skill_opportunity",
                summary=f"Repeated task pattern may become a skill: {pattern}",
                evidence_ids=evidence_ids,
                metadata={"pattern": pattern, "count": str(len(evidence_ids))},
            )
        )
    return findings


def _parse_memory_field_value(content: str) -> tuple[str, str] | None:
    prefix = "User "
    marker = " is "
    if not content.startswith(prefix) or marker not in content:
        return None
    field, value = content[len(prefix) :].split(marker, 1)
    field = field.strip().casefold()
    value = value.strip()
    if not field or not value:
        return None
    return field, value


def _event_evidence_id(event: observability.TraceEvent) -> str:
    return event.id or event.run_id
