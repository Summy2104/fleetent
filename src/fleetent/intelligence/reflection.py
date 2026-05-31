"""Reflection report public API."""

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fleetent import memory_layer, observability
from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

FindingType = Literal["memory_candidate", "memory_conflict", "skill_opportunity"]


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


async def _read_memory_signals(
    scope: str, events: list[observability.TraceEvent]
) -> list[memory_layer.MemoryItem]:
    query = _events_to_text(events)
    if not query:
        return []
    return await memory_layer.search(scope, query, limit=10)


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
    events: list[observability.TraceEvent], memory_signals: list[memory_layer.MemoryItem]
) -> list[ReflectionFinding]:
    findings: list[ReflectionFinding] = []
    findings.extend(_memory_candidate_findings(events, memory_signals))
    findings.extend(_memory_conflict_findings(memory_signals))
    findings.extend(_skill_opportunity_findings(events))
    return findings


def _memory_candidate_findings(
    events: list[observability.TraceEvent], memory_signals: list[memory_layer.MemoryItem]
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
    memory_signals: list[memory_layer.MemoryItem],
) -> list[ReflectionFinding]:
    by_field: dict[str, dict[str, list[memory_layer.MemoryItem]]] = {}
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
