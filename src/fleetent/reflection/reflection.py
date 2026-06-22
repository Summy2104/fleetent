"""Reflection report public API."""

import asyncio
import json
import os
import re
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

import yaml

from fleetent import memory, observability
from fleetent.db import SQLiteDatabase
from fleetent.governance import approval_request_store

FindingType = Literal["memory_candidate", "memory_conflict", "skill_opportunity"]
KnowledgeBaseFindingType = Literal[
    "missing_knowledge",
    "stale_document",
    "low_retrieval_quality",
    "connector_sync_issue",
    "entity_graph_gap",
    "insufficient_signal",
]
KnowledgeBaseFindingSeverity = Literal["low", "medium", "high"]
SkillProposalType = Literal["create_skill", "update_skill", "deprecate_skill"]
SkillProposalStatus = Literal["pending", "approved", "rejected", "applied"]
SkillProposalRisk = Literal["low", "medium", "high"]
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
ReflectionTrendGranularity = Literal["day", "week"]
ReflectionTrendDomain = Literal["memory", "knowledge_base", "skill"]
ProposalDomain = Literal["memory", "skill"]


def __getattr__(name: str) -> Any:
    if name == "knowledge_base":
        from fleetent import knowledge_base as _knowledge_base

        return _knowledge_base
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_MUTATING_ACTIONS = {"mark_stale", "merge", "rewrite", "compact", "delete"}


def _default_approval_outbound_connectors_provider() -> dict[str, Any]:
    return {}


_approval_outbound_connectors_provider: Callable[
    [],
    dict[str, Any],
] = _default_approval_outbound_connectors_provider


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
class KnowledgeBaseReflectionFinding:
    """A read-only Knowledge Base quality finding."""

    type: KnowledgeBaseFindingType
    severity: KnowledgeBaseFindingSeverity
    affected_resource: str
    evidence_refs: list[str]
    recommendation: str
    metadata: dict[str, str]


@dataclass(frozen=True)
class KnowledgeBaseReflectionReport:
    """A Knowledge Base quality report for one scope and time window."""

    id: str
    scope: str
    time_window: tuple[datetime, datetime]
    findings: list[KnowledgeBaseReflectionFinding]
    created_at: datetime
    signal_summary: dict[str, int | str]


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
    actor_user_id: str | None = None
    applied_at: datetime | None = None
    report_id: str | None = None


@dataclass(frozen=True)
class SkillProposal:
    """Owner-reviewed proposal to create, update, or deprecate a Skill."""

    id: str
    type: SkillProposalType
    target_skill: str
    reason: str
    evidence_refs: list[str]
    risk_level: SkillProposalRisk
    suggested_draft: str | None
    suggested_diff: str | None
    status: SkillProposalStatus
    created_at: datetime
    updated_at: datetime
    reviewer_user_id: str | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    actor_user_id: str | None = None
    applied_at: datetime | None = None
    files: dict[str, str] | None = None
    report_id: str | None = None


@dataclass(frozen=True)
class ReflectionTrendQuery:
    """Query parameters for an on-demand reflection trend summary."""

    scope: str
    start_ts: datetime
    end_ts: datetime
    bucket: ReflectionTrendGranularity = "week"
    domains: tuple[ReflectionTrendDomain, ...] = ("memory", "knowledge_base", "skill")


@dataclass(frozen=True)
class ReflectionTrendBucket:
    """Aggregate reflection signals for one UTC trend bucket."""

    start_ts: datetime
    end_ts: datetime
    finding_counts: dict[str, int]
    proposal_status_counts: dict[str, int]
    applied_count: int
    rejected_count: int
    proposal_risk_counts: dict[str, int]
    proposal_type_counts: dict[str, int]
    proposal_action_counts: dict[str, int]
    applied_ratio: float | None = None
    rejected_ratio: float | None = None


@dataclass(frozen=True)
class ReflectionTrendSummary:
    """On-demand aggregate trend summary for reflection-owned signals."""

    query: ReflectionTrendQuery
    buckets: list[ReflectionTrendBucket]
    top_findings: list[str]


@dataclass(frozen=True)
class ReflectionProposalRecord:
    """Unified reflection proposal list row across memory and skill domains."""

    id: str
    domain: ProposalDomain
    kind: str
    status: str
    subject_user_id: str | None
    target_ref: str | None
    risk: str
    created_at: datetime
    updated_at: datetime
    report_id: str | None = None


def get_reflection_trend_summary(query: ReflectionTrendQuery) -> ReflectionTrendSummary:
    """Aggregate reflection-owned reports and proposal lifecycle records."""
    bucket_ranges = _trend_bucket_ranges(query)
    buckets = [
        ReflectionTrendBucket(
            start_ts=start_ts,
            end_ts=end_ts,
            finding_counts={},
            proposal_status_counts={},
            applied_count=0,
            rejected_count=0,
            proposal_risk_counts={},
            proposal_type_counts={},
            proposal_action_counts={},
        )
        for start_ts, end_ts in bucket_ranges
    ]
    total_finding_counts: dict[str, int] = {}
    if "memory" in query.domains or "skill" in query.domains:
        _aggregate_report_findings(
            buckets,
            bucket_ranges,
            query,
            table_name="reflection_reports",
            total_finding_counts=total_finding_counts,
            domains=("memory", "skill"),
        )
    if "knowledge_base" in query.domains:
        _aggregate_report_findings(
            buckets,
            bucket_ranges,
            query,
            table_name="reflection_reports",
            total_finding_counts=total_finding_counts,
            domains=("knowledge_base",),
        )
    if "memory" in query.domains:
        _aggregate_memory_proposals(buckets, bucket_ranges, query)
    if "skill" in query.domains:
        _aggregate_skill_proposals(buckets, bucket_ranges, query)
    buckets = [_with_proposal_ratios(bucket) for bucket in buckets]
    top_findings = [
        finding_type
        for finding_type, _count in sorted(
            total_finding_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    return ReflectionTrendSummary(query=query, buckets=buckets, top_findings=top_findings)


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
    for memory_proposal in generate_memory_maintenance_proposals(
        scope,
        findings,
        report_id=report.id,
    ):
        _persist_memory_maintenance_proposal(memory_proposal)
    for skill_proposal in generate_skill_proposals(findings=findings, report_id=report.id):
        _persist_skill_proposal(skill_proposal)
    return report


async def run_kb_reflection_report(scope: str) -> KnowledgeBaseReflectionReport:
    """Generate a read-only Knowledge Base quality report."""
    now = datetime.now(UTC).replace(microsecond=0)
    start = now - timedelta(days=7)
    events = list(
        observability.query_trace_events(
            observability.TraceQuery(tenant_id=scope, start_ts=start, end_ts=now)
        )
    )
    findings = _generate_kb_findings(events)
    findings.extend(_connector_findings())
    if not events and not findings:
        findings.append(
            KnowledgeBaseReflectionFinding(
                type="insufficient_signal",
                severity="low",
                affected_resource=f"tenant:{scope}",
                evidence_refs=[],
                recommendation="Enable KB retrieval traces or connector status checks.",
                metadata={"reason": "no_kb_signals"},
            )
        )

    report = KnowledgeBaseReflectionReport(
        id=str(uuid.uuid4()),
        scope=scope,
        time_window=(start, now),
        findings=findings,
        created_at=now,
        signal_summary={
            "trace_count": len(events),
            "finding_count": len(findings),
            "scope": scope,
        },
    )
    _save_kb_reflection_report(report)
    return report


def generate_memory_maintenance_proposals(
    user_id: str,
    findings: list[ReflectionFinding],
    *,
    report_id: str | None = None,
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
                    _build_memory_maintenance_proposal(
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
                        report_id=report_id,
                    )
                )
                continue
            proposals.append(
                _build_memory_maintenance_proposal(
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
                    report_id=report_id,
                )
            )
            continue
        if finding.type == "memory_conflict":
            proposals.append(
                _build_memory_maintenance_proposal(
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
                    report_id=report_id,
                )
            )
    return proposals


def generate_skill_proposals(
    *,
    findings: list[ReflectionFinding] | None = None,
    skill_signals: list[dict[str, object]] | None = None,
    report_id: str | None = None,
) -> list[SkillProposal]:
    """Generate pending Skill proposals without applying them."""
    proposals: list[SkillProposal] = []
    for finding in findings or []:
        if finding.type != "skill_opportunity" or len(finding.evidence_ids) < 2:
            continue
        pattern = finding.metadata.get("pattern") or finding.summary.rsplit(":", 1)[-1].strip()
        target_skill = _skill_name(pattern)
        proposals.append(
            _create_skill_proposal(
                proposal_type="create_skill",
                target_skill=target_skill,
                reason=finding.summary,
                evidence_refs=finding.evidence_ids,
                risk_level="medium",
                files={"SKILL.md": _skill_draft(target_skill, pattern, finding.summary)},
                suggested_draft=_skill_draft(target_skill, pattern, finding.summary),
                suggested_diff=None,
                report_id=report_id,
            )
        )

    for signal in skill_signals or []:
        skill_name = str(signal.get("skill_name", "")).strip()
        if not skill_name:
            continue
        trigger_count = _int_signal(signal, "trigger_count")
        failure_count = _int_signal(signal, "failure_count")
        days_unused = _int_signal(signal, "days_unused")
        reason = str(signal.get("reason") or "deterministic skill quality signal")
        if trigger_count >= 5 and failure_count >= max(3, trigger_count // 3):
            proposals.append(
                _create_skill_proposal(
                    proposal_type="update_skill",
                    target_skill=skill_name,
                    reason=reason,
                    evidence_refs=[skill_name],
                    risk_level="medium",
                    files=None,
                    suggested_draft=None,
                    suggested_diff=_skill_diff(skill_name, reason),
                    report_id=report_id,
                )
            )
        elif trigger_count == 0 and days_unused >= 90:
            proposals.append(
                _create_skill_proposal(
                    proposal_type="deprecate_skill",
                    target_skill=skill_name,
                    reason=reason,
                    evidence_refs=[skill_name],
                    risk_level="low",
                    files=None,
                    suggested_draft=None,
                    suggested_diff=(
                        f"Mark skill {skill_name!r} deprecated after {days_unused} unused days."
                    ),
                    report_id=report_id,
                )
            )
    return proposals


def get_skill_proposal(proposal_id: str) -> SkillProposal:
    """Load one Skill proposal by id."""
    proposal = _get_skill_proposal(proposal_id)
    if proposal is None:
        raise ValueError("skill proposal does not exist")
    return proposal


def list_skill_proposals(status: str | None = "pending") -> list[SkillProposal]:
    """List Skill proposals, newest first; ``status=None`` returns every status."""
    database = _database()
    if not database.path.exists() or not _has_table(database, "reflection_proposals"):
        return []
    rows = database.execute(
        """
        SELECT * FROM reflection_proposals
        WHERE domain = 'skill'
        ORDER BY updated_at DESC
        """,
    ).fetchall()
    proposals = [_skill_proposal_from_row(row) for row in rows]
    if status is None:
        return proposals
    return [proposal for proposal in proposals if proposal.status == status]


def list_reflection_proposals(
    *,
    status: str | None = "pending",
    domain: ProposalDomain | None = None,
) -> list[ReflectionProposalRecord]:
    """List unified reflection proposals across domains."""
    database = _database()
    if not database.path.exists() or not _has_table(database, "reflection_proposals"):
        return []
    clauses: list[str] = []
    params: dict[str, object] = {}
    if domain is not None:
        clauses.append("domain = :domain")
        params["domain"] = domain
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = database.execute(
        f"""
        SELECT
            id, domain, kind, subject_user_id, target_ref, risk, applied_at, created_at, updated_at,
            report_id
        FROM reflection_proposals
        {where}
        ORDER BY updated_at DESC, id ASC
        """,
        params,
    ).fetchall()
    records = [
        ReflectionProposalRecord(
            id=str(row["id"]),
            domain=cast(ProposalDomain, row["domain"]),
            kind=str(row["kind"]),
            status=_proposal_status_for_row(row),
            subject_user_id=cast(str | None, row["subject_user_id"]),
            target_ref=cast(str | None, row["target_ref"]),
            risk=str(row["risk"]),
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
            report_id=cast(str | None, row["report_id"]),
        )
        for row in rows
    ]
    if status is None:
        return records
    return [record for record in records if record.status == status]


def approve_skill_proposal(proposal_id: str, *, reviewer_user_id: str) -> SkillProposal:
    """Approve a pending Skill proposal."""
    proposal = get_skill_proposal(proposal_id)
    _require_skill_proposal_status(proposal, {"pending"})
    _decide_proposal_approval_request(
        proposal_id=proposal_id,
        status="approved",
        approver_user_id=reviewer_user_id,
    )
    now = datetime.now(UTC).replace(microsecond=0)
    updated = _replace_skill_proposal(
        proposal,
        status="approved",
        reviewer_user_id=reviewer_user_id,
        reviewed_at=now,
        updated_at=now,
    )
    _update_skill_proposal(updated)
    return updated


def reject_skill_proposal(
    proposal_id: str,
    *,
    reviewer_user_id: str,
    reason: str,
) -> SkillProposal:
    """Reject a pending Skill proposal."""
    proposal = get_skill_proposal(proposal_id)
    _require_skill_proposal_status(proposal, {"pending"})
    _decide_proposal_approval_request(
        proposal_id=proposal_id,
        status="rejected",
        approver_user_id=reviewer_user_id,
        reason=reason,
    )
    now = datetime.now(UTC).replace(microsecond=0)
    updated = _replace_skill_proposal(
        proposal,
        status="rejected",
        reviewer_user_id=reviewer_user_id,
        reviewed_at=now,
        rejection_reason=reason,
        updated_at=now,
    )
    _update_skill_proposal(updated)
    return updated


async def apply_skill_proposal(proposal_id: str, *, actor_user_id: str) -> SkillProposal:
    """Apply an approved Skill proposal through the Skill boundary."""
    proposal = get_skill_proposal(proposal_id)
    if proposal.status == "rejected":
        raise ValueError("cannot apply rejected skill proposal")
    _require_skill_proposal_status(proposal, {"approved"})
    await apply_skill_proposal_to_boundary(proposal)
    now = datetime.now(UTC).replace(microsecond=0)
    updated = _replace_skill_proposal(
        proposal,
        status="applied",
        actor_user_id=actor_user_id,
        applied_at=now,
        updated_at=now,
    )
    _update_skill_proposal(updated)
    return updated


async def apply_skill_proposal_to_boundary(proposal: SkillProposal) -> None:
    """Apply a Skill proposal through the Skill management boundary."""
    from fleetent.skills import SkillWriteProvenance, write_skill
    from fleetent.skills import registry as skill_registry

    if proposal.type in {"create_skill", "update_skill"}:
        files = proposal.files or {}
        if "SKILL.md" not in files and proposal.suggested_draft is not None:
            files = {"SKILL.md": proposal.suggested_draft, **files}
        if "SKILL.md" not in files:
            raise ValueError("skill proposal bundle must include SKILL.md")
        write_skill(
            proposal.target_skill,
            files,
            SkillWriteProvenance(
                source="reflection",
                proposal_id=proposal.id,
                applied_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
            ),
        )
        skill_registry.reload()
        return

    if proposal.type == "deprecate_skill":
        files = _load_existing_skill_bundle(proposal.target_skill)
        files["SKILL.md"] = _disable_skill_markdown(files["SKILL.md"])
        write_skill(
            proposal.target_skill,
            files,
            SkillWriteProvenance(
                source="reflection",
                proposal_id=proposal.id,
                applied_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
            ),
        )
        skill_registry.reload()
        return

    raise ValueError(f"unsupported skill proposal type: {proposal.type}")


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
    """Create and persist a pending User Memory maintenance proposal."""
    proposal = _build_memory_maintenance_proposal(
        user_id=user_id,
        action=action,
        target_memory_ids=target_memory_ids,
        proposed_content=proposed_content,
        risk=risk,
        reason=reason,
        evidence_ids=evidence_ids,
        metadata_patch=metadata_patch,
        expires_at=expires_at,
    )
    _insert_maintenance_proposal(proposal)
    _create_proposal_approval_request(
        proposal_id=proposal.id,
        domain="memory",
        risk=proposal.risk,
        created_at=proposal.created_at,
        expires_at=proposal.expires_at,
    )
    _schedule_pending_proposal_notification(
        proposal_id=proposal.id,
        domain="memory",
        risk=proposal.risk,
    )
    _record_maintenance_event("memory_maintenance_proposal_created", proposal)
    return proposal


def _build_memory_maintenance_proposal(
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
    report_id: str | None = None,
) -> MemoryMaintenanceProposal:
    """Build a pending User Memory maintenance proposal without side effects."""
    _validate_proposal_input(user_id, action, risk, target_memory_ids)
    now = datetime.now(UTC).replace(microsecond=0)
    return MemoryMaintenanceProposal(
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
        actor_user_id=None,
        applied_at=None,
        report_id=report_id,
    )


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
    clauses = ["domain = 'memory'", "subject_user_id = :user_id"]
    params: dict[str, object] = {"user_id": user_id}
    rows = (
        _database()
        .execute(
            f"""
            SELECT *
            FROM reflection_proposals
            WHERE {" AND ".join(clauses)}
            ORDER BY updated_at DESC, id ASC
            """,
            params,
        )
        .fetchall()
    )
    proposals = [_proposal_from_row(row) for row in rows]
    if status is None:
        return proposals
    return [proposal for proposal in proposals if proposal.status == status]


def approve_memory_maintenance_proposal(
    proposal_id: str,
    *,
    actor_user_id: str,
) -> MemoryMaintenanceProposal:
    """Approve a pending proposal as the User Memory owner."""
    proposal = get_memory_maintenance_proposal(proposal_id)
    _require_owner(proposal, actor_user_id)
    _require_status(proposal, {"pending"})
    _decide_proposal_approval_request(
        proposal_id=proposal_id,
        status="approved",
        approver_user_id=actor_user_id,
    )
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
    _decide_proposal_approval_request(
        proposal_id=proposal_id,
        status="rejected",
        approver_user_id=actor_user_id,
        reason=f"proposal {proposal_id} rejected by owner",
    )
    updated = _with_status(proposal, "rejected")
    _update_maintenance_proposal(updated)
    _record_maintenance_event("memory_maintenance_proposal_rejected", updated)
    return updated


def expire_memory_maintenance_proposal(proposal_id: str) -> MemoryMaintenanceProposal:
    """Expire a proposal that is no longer actionable."""
    proposal = get_memory_maintenance_proposal(proposal_id)
    _require_status(proposal, {"pending", "approved"})
    _decide_proposal_approval_request(
        proposal_id=proposal_id,
        status="expired",
    )
    updated = _with_status(proposal, "expired")
    _update_maintenance_proposal(updated)
    return updated


def mark_shared_memory_proposal_applied(proposal_id: str) -> MemoryMaintenanceProposal:
    """Mark an approved Shared Memory suggestion applied without User Memory owner mutation."""
    proposal = get_memory_maintenance_proposal(proposal_id)
    _require_status(proposal, {"approved"})
    if proposal.action != "suggest_shared_memory_or_kb":
        raise ValueError("proposal is not a shared memory suggestion")
    if proposal.metadata_patch.get("target") != "shared_memory":
        raise ValueError("proposal target is not shared_memory")
    updated = _with_status(proposal, "applied")
    updated = replace(
        updated,
        actor_user_id=proposal.user_id,
        applied_at=datetime.now(UTC).replace(microsecond=0),
    )
    _update_maintenance_proposal(updated)
    _record_maintenance_event("shared_memory_proposal_applied", updated)
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
    updated = replace(
        updated,
        actor_user_id=actor_user_id,
        applied_at=datetime.now(UTC).replace(microsecond=0),
    )
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
            id, domain, scope, time_window_start, time_window_end, findings_json,
            signal_summary_json, created_at
        )
        VALUES (
            :id, :domain, :scope, :time_window_start, :time_window_end, :findings_json,
            :signal_summary_json, :created_at
        )
        """,
        {
            "id": report.id,
            "domain": "memory",
            "scope": report.scope,
            "time_window_start": report.time_window[0].isoformat(),
            "time_window_end": report.time_window[1].isoformat(),
            "findings_json": _findings_json(report.findings),
            "signal_summary_json": None,
            "created_at": report.created_at.isoformat(),
        },
    )


def _save_kb_reflection_report(report: KnowledgeBaseReflectionReport) -> None:
    database = _database()
    if not database.path.exists():
        return
    if not _has_table(database, "reflection_reports"):
        return
    database.execute(
        """
        INSERT INTO reflection_reports (
            id, domain, scope, time_window_start, time_window_end, findings_json,
            signal_summary_json, created_at
        )
        VALUES (
            :id, :domain, :scope, :time_window_start, :time_window_end, :findings_json,
            :signal_summary_json, :created_at
        )
        """,
        {
            "id": report.id,
            "domain": "knowledge_base",
            "scope": report.scope,
            "time_window_start": report.time_window[0].isoformat(),
            "time_window_end": report.time_window[1].isoformat(),
            "findings_json": _kb_findings_json(report.findings),
            "signal_summary_json": json.dumps(
                report.signal_summary,
                ensure_ascii=False,
                sort_keys=True,
            ),
            "created_at": report.created_at.isoformat(),
        },
    )


def _persist_memory_maintenance_proposal(proposal: MemoryMaintenanceProposal) -> None:
    database = _database()
    if not database.path.exists():
        return
    if not _has_table(database, "reflection_proposals"):
        return
    _insert_maintenance_proposal(proposal)
    _create_proposal_approval_request(
        proposal_id=proposal.id,
        domain="memory",
        risk=proposal.risk,
        created_at=proposal.created_at,
        expires_at=proposal.expires_at,
    )
    _schedule_pending_proposal_notification(
        proposal_id=proposal.id,
        domain="memory",
        risk=proposal.risk,
    )
    _record_maintenance_event("memory_maintenance_proposal_created", proposal)


def _persist_skill_proposal(proposal: SkillProposal) -> None:
    database = _database()
    if not database.path.exists():
        return
    if not _has_table(database, "reflection_proposals"):
        return
    _insert_skill_proposal(proposal)
    _create_proposal_approval_request(
        proposal_id=proposal.id,
        domain="skill",
        risk=proposal.risk_level,
        created_at=proposal.created_at,
        expires_at=None,
    )
    _schedule_pending_proposal_notification(
        proposal_id=proposal.id,
        domain="skill",
        risk=proposal.risk_level,
    )


def _trend_bucket_ranges(query: ReflectionTrendQuery) -> list[tuple[datetime, datetime]]:
    start_ts = _as_utc(query.start_ts)
    end_ts = _as_utc(query.end_ts)
    if end_ts <= start_ts:
        raise ValueError("trend query end_ts must be after start_ts")

    if query.bucket == "day":
        step = timedelta(days=1)
    elif query.bucket == "week":
        step = timedelta(days=7)
    else:
        raise ValueError(f"unsupported trend bucket: {query.bucket}")

    ranges: list[tuple[datetime, datetime]] = []
    current = start_ts
    while current < end_ts:
        next_ts = min(current + step, end_ts)
        ranges.append((current, next_ts))
        current = next_ts
    return ranges


def _aggregate_report_findings(
    buckets: list[ReflectionTrendBucket],
    bucket_ranges: list[tuple[datetime, datetime]],
    query: ReflectionTrendQuery,
    *,
    table_name: str,
    total_finding_counts: dict[str, int],
    domains: tuple[str, ...] | None = None,
) -> None:
    database = _database()
    if not database.path.exists() or not _has_table(database, table_name):
        return
    params = {
        "scope": query.scope,
        "start_ts": _as_utc(query.start_ts).isoformat(),
        "end_ts": _as_utc(query.end_ts).isoformat(),
    }
    domain_where = ""
    if domains is not None:
        placeholders = []
        for index, domain in enumerate(domains):
            key = f"domain_{index}"
            params[key] = domain
            placeholders.append(f":{key}")
        domain_where = f" AND domain IN ({', '.join(placeholders)})"
    rows = database.execute(
        f"""
        SELECT findings_json, created_at
        FROM {table_name}
        WHERE scope = :scope
          AND created_at >= :start_ts
          AND created_at < :end_ts
          {domain_where}
        ORDER BY created_at ASC
        """,
        params,
    ).fetchall()
    for row in rows:
        bucket_index = _trend_bucket_index(
            _parse_datetime(row["created_at"]),
            bucket_ranges,
        )
        if bucket_index is None:
            continue
        for finding in _trend_findings_from_json(str(row["findings_json"])):
            finding_type = finding.get("type")
            if not isinstance(finding_type, str) or not finding_type:
                continue
            _increment_count(buckets[bucket_index].finding_counts, finding_type)
            _increment_count(total_finding_counts, finding_type)


def _aggregate_memory_proposals(
    buckets: list[ReflectionTrendBucket],
    bucket_ranges: list[tuple[datetime, datetime]],
    query: ReflectionTrendQuery,
) -> None:
    database = _database()
    if not database.path.exists() or not _has_table(database, "reflection_proposals"):
        return
    rows = database.execute(
        """
        SELECT id, kind, risk, applied_at, created_at
        FROM reflection_proposals
        WHERE domain = 'memory'
          AND subject_user_id = :scope
          AND created_at >= :start_ts
          AND created_at < :end_ts
        ORDER BY created_at ASC
        """,
        _trend_time_params(query),
    ).fetchall()
    for row in rows:
        bucket_index = _trend_bucket_index(_parse_datetime(row["created_at"]), bucket_ranges)
        if bucket_index is None:
            continue
        bucket = buckets[bucket_index]
        status = _proposal_status_for_row(row)
        _increment_count(bucket.proposal_status_counts, status)
        _increment_count(bucket.proposal_risk_counts, str(row["risk"]))
        _increment_count(bucket.proposal_action_counts, str(row["kind"]))
        if status == "applied":
            _increment_bucket_attr(bucket, "applied_count")
        if status == "rejected":
            _increment_bucket_attr(bucket, "rejected_count")


def _aggregate_skill_proposals(
    buckets: list[ReflectionTrendBucket],
    bucket_ranges: list[tuple[datetime, datetime]],
    query: ReflectionTrendQuery,
) -> None:
    if query.scope not in {"global", "*"}:
        return
    database = _database()
    if not database.path.exists() or not _has_table(database, "reflection_proposals"):
        return
    rows = database.execute(
        """
        SELECT id, kind, risk, applied_at, created_at
        FROM reflection_proposals
        WHERE domain = 'skill'
          AND created_at >= :start_ts
          AND created_at < :end_ts
        ORDER BY created_at ASC
        """,
        _trend_time_params(query),
    ).fetchall()
    for row in rows:
        bucket_index = _trend_bucket_index(_parse_datetime(row["created_at"]), bucket_ranges)
        if bucket_index is None:
            continue
        bucket = buckets[bucket_index]
        status = _proposal_status_for_row(row)
        _increment_count(bucket.proposal_status_counts, status)
        _increment_count(bucket.proposal_risk_counts, str(row["risk"]))
        _increment_count(bucket.proposal_type_counts, str(row["kind"]))
        if status == "applied":
            _increment_bucket_attr(bucket, "applied_count")
        if status == "rejected":
            _increment_bucket_attr(bucket, "rejected_count")


def _with_proposal_ratios(bucket: ReflectionTrendBucket) -> ReflectionTrendBucket:
    proposal_count = sum(bucket.proposal_status_counts.values())
    if proposal_count == 0:
        return bucket
    return replace(
        bucket,
        applied_ratio=bucket.applied_count / proposal_count,
        rejected_ratio=bucket.rejected_count / proposal_count,
    )


def _trend_time_params(query: ReflectionTrendQuery) -> dict[str, str]:
    return {
        "scope": query.scope,
        "start_ts": _as_utc(query.start_ts).isoformat(),
        "end_ts": _as_utc(query.end_ts).isoformat(),
    }


def _trend_findings_from_json(payload: str) -> list[dict[str, object]]:
    parsed = json.loads(payload)
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _trend_bucket_index(
    value: datetime,
    bucket_ranges: list[tuple[datetime, datetime]],
) -> int | None:
    normalized = _as_utc(value)
    for index, (start_ts, end_ts) in enumerate(bucket_ranges):
        if start_ts <= normalized < end_ts:
            return index
    return None


def _increment_count(counts: dict[str, int], key: str, amount: int = 1) -> None:
    counts[key] = counts.get(key, 0) + amount


def _increment_bucket_attr(
    bucket: ReflectionTrendBucket,
    attr: Literal["applied_count", "rejected_count"],
) -> None:
    object.__setattr__(bucket, attr, getattr(bucket, attr) + 1)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


_state_db: SQLiteDatabase | None = None


def set_state_db(db: SQLiteDatabase) -> None:
    """Inject the per-agent state DB.  Called once at agent boot via agent_app."""
    global _state_db
    _state_db = db
    approval_request_store.set_state_db(db)


def _database() -> SQLiteDatabase:
    """Return the per-agent state DB injected at boot.

    No management-DB fallback: without a per-agent ``_state_db`` injection, reflection
    refuses rather than reading/writing agent-side ``reflection_reports`` /
    ``reflection_proposals`` in the shared management library — that would violate the
    agent/platform data-isolation contract.
    """
    if _state_db is None:
        raise RuntimeError("reflection: state_db not initialized — call set_state_db(db) at boot")
    return _state_db


def _schedule_pending_proposal_notification(
    *,
    proposal_id: str,
    domain: ProposalDomain,
    risk: str,
) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(
        _notify_pending_proposal(
            proposal_id=proposal_id,
            domain=domain,
            risk=risk,
        )
    )


async def _notify_pending_proposal(
    *,
    proposal_id: str,
    domain: ProposalDomain,
    risk: str,
) -> None:
    from fleetent import agent_config
    from fleetent.governance.permission_gate import PermissionGate

    active_agent = agent_config.active_agent()
    approval_routing = None if active_agent is None else active_agent.approval
    if approval_routing is None:
        return

    tool_name = f"reflection_{domain}_proposal"
    addresses, _policy = agent_config.resolve_approvers(approval_routing, risk, tool_name)
    addresses = [(platform, target) for platform, target in addresses if platform != "requester"]
    if not addresses:
        return

    gate = PermissionGate()
    await gate._notify_approvers(
        approval_id=proposal_id,
        tool_name=tool_name,
        risk_level=risk,
        approval_routing=approval_routing,
        outbound_connectors=_approval_outbound_connectors_provider(),
    )


def _has_reflection_reports_table(database: SQLiteDatabase) -> bool:
    return _has_table(database, "reflection_reports")


def _has_table(database: SQLiteDatabase, name: str) -> bool:
    row = database.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = :type AND name = :name
        """,
        {"type": "table", "name": name},
    ).fetchone()
    return row is not None


def _findings_json(findings: list[ReflectionFinding]) -> str:
    payload = [asdict(finding) for finding in findings]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _kb_findings_json(findings: list[KnowledgeBaseReflectionFinding]) -> str:
    payload = [asdict(finding) for finding in findings]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _generate_kb_findings(
    events: list[observability.TraceEvent],
) -> list[KnowledgeBaseReflectionFinding]:
    findings: list[KnowledgeBaseReflectionFinding] = []
    for event in events:
        payload = event.payload
        event_id = event.id or event.run_id
        query = str(payload.get("query") or payload.get("question") or "unknown query")
        if _int_payload(payload, "result_count") == 0:
            findings.append(
                _kb_finding(
                    "missing_knowledge",
                    "high",
                    f"query:{query}",
                    [event_id],
                    "Add or sync KB content that answers this repeated zero-result query.",
                    {"query": query},
                )
            )
            continue
        if payload.get("stale_document_id"):
            findings.append(
                _kb_finding(
                    "stale_document",
                    "medium",
                    f"document:{payload['stale_document_id']}",
                    [event_id],
                    "Review and refresh the stale source document.",
                    {"query": query},
                )
            )
        if _low_quality_signal(payload):
            findings.append(
                _kb_finding(
                    "low_retrieval_quality",
                    "medium",
                    f"query:{query}",
                    [event_id],
                    "Improve source attribution, chunking, or retrieval ranking for this topic.",
                    {"query": query},
                )
            )
        if _graph_gap_signal(query, payload):
            findings.append(
                _kb_finding(
                    "entity_graph_gap",
                    "medium",
                    f"query:{query}",
                    [event_id],
                    "Run entity extraction or add relation evidence for this relationship query.",
                    {"query": query},
                )
            )
    return findings


def _connector_findings() -> list[KnowledgeBaseReflectionFinding]:
    from typing import Any, cast

    from fleetent import knowledge_base

    findings: list[KnowledgeBaseReflectionFinding] = []
    kb_api = cast(Any, knowledge_base)
    try:
        connectors = kb_api.list_configured_connectors()
    except Exception:
        return [
            _kb_finding(
                "insufficient_signal",
                "low",
                "knowledge_base:connectors",
                [],
                "Check knowledge-base availability before running KB reflection.",
                {"reason": "knowledge_base_unavailable"},
            )
        ]
    for connector in connectors:
        connector_id = str(getattr(connector, "connector_id", "unknown"))
        try:
            status = kb_api.get_connector_status(connector_id)
        except Exception:
            findings.append(
                _kb_finding(
                    "insufficient_signal",
                    "low",
                    f"connector:{connector_id}",
                    [connector_id],
                    "Check connector status API availability before running KB reflection.",
                    {"reason": "connector_status_unavailable"},
                )
            )
            continue
        status_value = str(getattr(status, "status", "unknown"))
        error_summary = str(getattr(status, "error_summary", "") or "")
        if status_value in {"failed", "stale"} or error_summary:
            findings.append(
                _kb_finding(
                    "connector_sync_issue",
                    "high" if status_value == "failed" else "medium",
                    f"connector:{connector_id}",
                    [connector_id],
                    "Inspect connector credentials, scope, and latest sync failure.",
                    {"status": status_value, "error_summary": error_summary[:200]},
                )
            )
    return findings


def _kb_finding(
    finding_type: KnowledgeBaseFindingType,
    severity: KnowledgeBaseFindingSeverity,
    affected_resource: str,
    evidence_refs: list[str],
    recommendation: str,
    metadata: dict[str, str],
) -> KnowledgeBaseReflectionFinding:
    return KnowledgeBaseReflectionFinding(
        type=finding_type,
        severity=severity,
        affected_resource=affected_resource,
        evidence_refs=evidence_refs,
        recommendation=recommendation,
        metadata=metadata,
    )


def _low_quality_signal(payload: dict[str, Any]) -> bool:
    top_score = payload.get("top_score")
    if isinstance(top_score, int | float) and float(top_score) < 0.3:
        return True
    if _int_payload(payload, "source_attribution_count") == 0:
        return True
    return bool(payload.get("user_correction"))


def _graph_gap_signal(query: str, payload: dict[str, Any]) -> bool:
    normalized = query.casefold()
    relation_like = any(
        marker in normalized
        for marker in ("depends on", "dependency", "relation", "relationship", "connected to")
    )
    if not relation_like:
        return False
    return (
        _int_payload(payload, "graph_result_count") == 0
        or _int_payload(payload, "graph_evidence_count") == 0
    )


def _int_payload(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _insert_maintenance_proposal(proposal: MemoryMaintenanceProposal) -> None:
    _database().execute(
        """
        INSERT INTO reflection_proposals (
            id, domain, kind, report_id, subject_user_id, target_ref, payload_json,
            reason, evidence_json, risk, actor_user_id, applied_at, created_at, updated_at
        )
        VALUES (
            :id, :domain, :kind, :report_id, :subject_user_id, :target_ref, :payload_json,
            :reason, :evidence_json, :risk, :actor_user_id, :applied_at, :created_at, :updated_at
        )
        """,
        _proposal_params(proposal),
    )


def _create_skill_proposal(
    *,
    proposal_type: SkillProposalType,
    target_skill: str,
    reason: str,
    evidence_refs: list[str],
    risk_level: SkillProposalRisk,
    files: dict[str, str] | None,
    suggested_draft: str | None,
    suggested_diff: str | None,
    report_id: str | None = None,
) -> SkillProposal:
    proposal = _build_skill_proposal(
        proposal_type=proposal_type,
        target_skill=target_skill,
        reason=reason,
        evidence_refs=evidence_refs,
        risk_level=risk_level,
        files=files,
        suggested_draft=suggested_draft,
        suggested_diff=suggested_diff,
        report_id=report_id,
    )
    _persist_skill_proposal(proposal)
    return proposal


def _build_skill_proposal(
    *,
    proposal_type: SkillProposalType,
    target_skill: str,
    reason: str,
    evidence_refs: list[str],
    risk_level: SkillProposalRisk,
    files: dict[str, str] | None,
    suggested_draft: str | None,
    suggested_diff: str | None,
    report_id: str | None = None,
) -> SkillProposal:
    """Build a pending Skill proposal without persistence side effects."""
    now = datetime.now(UTC).replace(microsecond=0)
    return SkillProposal(
        id=str(uuid.uuid4()),
        type=proposal_type,
        target_skill=target_skill,
        reason=reason,
        evidence_refs=list(evidence_refs),
        risk_level=risk_level,
        files=None if files is None else dict(files),
        suggested_draft=suggested_draft,
        suggested_diff=suggested_diff,
        status="pending",
        created_at=now,
        updated_at=now,
        report_id=report_id,
    )


def _insert_skill_proposal(proposal: SkillProposal) -> None:
    database = _database()
    if not database.path.exists() or not _has_table(database, "reflection_proposals"):
        return
    database.execute(
        """
        INSERT OR IGNORE INTO reflection_proposals (
            id, domain, kind, report_id, subject_user_id, target_ref, payload_json,
            reason, evidence_json, risk, actor_user_id, applied_at, created_at, updated_at
        )
        VALUES (
            :id, :domain, :kind, :report_id, :subject_user_id, :target_ref, :payload_json,
            :reason, :evidence_json, :risk, :actor_user_id, :applied_at, :created_at, :updated_at
        )
        """,
        _skill_proposal_params(proposal),
    )


def _update_skill_proposal(proposal: SkillProposal) -> None:
    _database().execute(
        """
        UPDATE reflection_proposals
        SET actor_user_id = :actor_user_id,
            applied_at = :applied_at,
            updated_at = :updated_at
        WHERE id = :id
        """,
        _skill_proposal_params(proposal),
    )


def _get_skill_proposal(proposal_id: str) -> SkillProposal | None:
    row = (
        _database()
        .execute(
            """
            SELECT *
            FROM reflection_proposals
            WHERE id = :id AND domain = 'skill'
            """,
            {"id": proposal_id},
        )
        .fetchone()
    )
    return _skill_proposal_from_row(row) if row is not None else None


def _skill_proposal_params(proposal: SkillProposal) -> dict[str, object]:
    return {
        "id": proposal.id,
        "domain": "skill",
        "kind": proposal.type,
        "report_id": proposal.report_id,
        "subject_user_id": None,
        "target_ref": proposal.target_skill,
        "payload_json": json.dumps(
            {
                "files": proposal.files,
                "suggested_draft": proposal.suggested_draft,
                "suggested_diff": proposal.suggested_diff,
            },
            sort_keys=True,
        ),
        "reason": proposal.reason,
        "evidence_json": json.dumps(proposal.evidence_refs, sort_keys=True),
        "risk": proposal.risk_level,
        "actor_user_id": proposal.actor_user_id,
        "applied_at": proposal.applied_at.isoformat() if proposal.applied_at else None,
        "created_at": proposal.created_at.isoformat(),
        "updated_at": proposal.updated_at.isoformat(),
    }


def _skill_proposal_from_row(row: dict[str, Any]) -> SkillProposal:
    payload = json.loads(str(row["payload_json"]))
    return SkillProposal(
        id=str(row["id"]),
        type=cast(SkillProposalType, row["kind"]),
        target_skill=str(row["target_ref"]),
        reason=str(row["reason"]),
        evidence_refs=list(json.loads(str(row["evidence_json"]))),
        risk_level=cast(SkillProposalRisk, row["risk"]),
        files=(
            {str(key): str(value) for key, value in dict(payload.get("files", {})).items()}
            if payload.get("files") is not None
            else None
        ),
        report_id=cast(str | None, row["report_id"]),
        suggested_draft=cast(str | None, payload.get("suggested_draft")),
        suggested_diff=cast(str | None, payload.get("suggested_diff")),
        status=cast(SkillProposalStatus, _proposal_status_for_row(row)),
        reviewer_user_id=_approval_request_value(row["id"], "approver_user_id"),
        reviewed_at=_approval_request_datetime(row["id"], "decided_at"),
        rejection_reason=_approval_request_value(row["id"], "reason"),
        actor_user_id=cast(str | None, row["actor_user_id"]),
        applied_at=_parse_optional_datetime(row["applied_at"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _replace_skill_proposal(proposal: SkillProposal, **changes: object) -> SkillProposal:
    data = asdict(proposal)
    data.update(changes)
    return SkillProposal(**data)


def _require_skill_proposal_status(
    proposal: SkillProposal,
    allowed: set[SkillProposalStatus],
) -> None:
    if proposal.status not in allowed:
        expected = ", ".join(sorted(allowed))
        raise ValueError(f"skill proposal must be {expected}, got {proposal.status}")


def _create_proposal_approval_request(
    *,
    proposal_id: str,
    domain: ProposalDomain,
    risk: str,
    created_at: datetime,
    expires_at: datetime | None,
) -> None:
    approval_request_store.create_request(
        id=proposal_id,
        subject_type="memory_proposal" if domain == "memory" else "skill_proposal",
        subject_id=proposal_id,
        requester_user_id=None,
        risk=risk,
        routing_key=f"reflection_{domain}_proposal",
        created_at=created_at.isoformat(),
        expires_at=_format_datetime(expires_at),
    )


def _decide_proposal_approval_request(
    *,
    proposal_id: str,
    status: Literal["approved", "rejected", "expired"],
    approver_user_id: str | None = None,
    reason: str | None = None,
) -> None:
    try:
        approval_request_store.decide_request(
            id=proposal_id,
            status=status,
            decided_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
            approver_user_id=approver_user_id,
            reason=reason,
        )
    except RuntimeError:
        # Unit tests still exercise pure row/dataclass helpers with fake stores that do
        # not provision approval_requests. Keep those paths working without a DB.
        return


def _approval_request_row(proposal_id: object) -> dict[str, Any] | None:
    try:
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
    value = _approval_request_value(proposal_id, key)
    return _parse_optional_datetime(value)


def _proposal_status_for_row(row: dict[str, Any]) -> str:
    if row.get("applied_at") is not None:
        return "applied"
    legacy_status = row.get("status")
    if legacy_status is not None:
        return str(legacy_status)
    proposal_id = row.get("id")
    if proposal_id is None:
        return "pending"
    request = _approval_request_row(proposal_id)
    if request is None:
        return "pending"
    return str(request["status"])


def _skill_name(pattern: str) -> str:
    words = re.findall(r"[a-z0-9]+", pattern.casefold())
    return "-".join(words[:6]) or "generated-skill"


def _skill_draft(skill_name: str, pattern: str, reason: str) -> str:
    return (
        "---\n"
        f"name: {skill_name}\n"
        f"description: Deterministic draft for {pattern}.\n"
        "---\n"
        f"## Purpose\n{reason}\n\n"
        "## Procedure\n- Review the evidence traces.\n- Encode the repeated workflow safely.\n"
    )


def _skill_diff(skill_name: str, reason: str) -> str:
    return f"Update {skill_name!r}: {reason}"


def _load_existing_skill_bundle(skill_name: str) -> dict[str, str]:
    from fleetent.skills import registry as skill_registry

    skills_root = Path(skill_registry._last_skills_dir or skill_registry._resolve_skills_dir(None))
    skill_dir = skills_root / skill_name
    if not skill_dir.is_dir():
        raise ValueError(f"skill {skill_name!r} does not exist")
    files: dict[str, str] = {}
    for path in skill_dir.rglob("*"):
        if path.is_file():
            files[str(path.relative_to(skill_dir))] = path.read_text(encoding="utf-8")
    return files


def _disable_skill_markdown(content: str) -> str:
    from fleetent.skills import registry as skill_registry

    frontmatter = skill_registry._parse_frontmatter(content)
    if frontmatter is None:
        raise ValueError("SKILL.md must contain valid frontmatter")
    frontmatter["enabled"] = False
    body = skill_registry._body_after_frontmatter(content).lstrip("\n")
    return f"---\n{yaml.safe_dump(frontmatter, sort_keys=False).strip()}\n---\n{body}"


def _int_signal(signal: dict[str, object], key: str) -> int:
    value = signal.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _real_skill_draft_enabled() -> bool:
    return os.getenv("FLEETENT_REFLECTION_REAL_SKILL_DRAFT", "").lower() in {
        "1",
        "true",
        "yes",
    }


def _update_maintenance_proposal(proposal: MemoryMaintenanceProposal) -> None:
    _database().execute(
        """
        UPDATE reflection_proposals
        SET updated_at = :updated_at,
            payload_json = :payload_json,
            evidence_json = :evidence_json,
            actor_user_id = :actor_user_id,
            applied_at = :applied_at
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
            FROM reflection_proposals
            WHERE id = :id AND domain = 'memory'
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
        "domain": "memory",
        "kind": proposal.action,
        "report_id": proposal.report_id,
        "subject_user_id": proposal.user_id,
        "target_ref": None,
        "payload_json": json.dumps(
            {
                "target_memory_ids": proposal.target_memory_ids,
                "proposed_content": proposal.proposed_content,
                "metadata_patch": proposal.metadata_patch,
            },
            sort_keys=True,
        ),
        "risk": proposal.risk,
        "reason": proposal.reason,
        "evidence_json": json.dumps(proposal.evidence_ids, sort_keys=True),
        "actor_user_id": proposal.actor_user_id,
        "applied_at": _format_datetime(proposal.applied_at),
        "created_at": _format_datetime(proposal.created_at),
        "updated_at": _format_datetime(proposal.updated_at),
    }


def _proposal_from_row(row: dict[str, Any]) -> MemoryMaintenanceProposal:
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
        actor_user_id=cast(str | None, row.get("actor_user_id")),
        applied_at=_parse_optional_datetime(row.get("applied_at")),
        report_id=cast(str | None, row["report_id"]),
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
        actor_user_id=proposal.actor_user_id,
        applied_at=proposal.applied_at,
        report_id=proposal.report_id,
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
        target = proposal.metadata_patch.get("target")
        if target == "shared_memory":
            from fleetent.memory import shared as shared_memory

            await shared_memory.apply_shared_memory_proposal(
                proposal.id,
                actor_id=proposal.user_id,
            )
            return
        if target == "knowledge_base":
            raise RuntimeError("knowledge base proposals are no longer handled on the agent side")
        if target is None:
            # Older proposals may not yet carry a concrete shared-memory / KB target.
            # Preserve the legacy "no user-memory write" behavior for those records.
            return
        raise ValueError("proposal target is not shared_memory")
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
