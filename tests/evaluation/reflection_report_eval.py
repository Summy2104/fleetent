import json
import os
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from fleetent.intelligence.memory import MemoryItem
from tests.integration.test_migrations import apply_migrations

REQUIRED_FIXTURE_FIELDS = (
    "name",
    "scope",
    "trace_events",
    "memory_signals",
    "expected_findings",
    "forbidden_findings",
    "forbidden_persisted_text",
)
_FINDING_TYPES = {"memory_candidate", "memory_conflict", "skill_opportunity"}
_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "reflection_report"


class FixtureValidationError(ValueError):
    """Raised when a reflection report evaluation fixture is invalid."""


@dataclass(frozen=True)
class ReflectionEvaluationResult:
    """Result captured from a deterministic reflection report evaluation run."""

    fixture: Mapping[str, Any]
    db_path: Path
    findings: list[dict[str, Any]]
    persisted_findings_json: str
    trace_query_user_ids: list[str | None]
    memory_queries: list[tuple[str, str, int]]


def validate_fixture(fixture: Mapping[str, Any]) -> None:
    """Validate the reflection report evaluation fixture schema."""
    missing = [field for field in REQUIRED_FIXTURE_FIELDS if field not in fixture]
    if missing:
        raise FixtureValidationError(f"missing required fixture fields: {', '.join(missing)}")

    _require_non_empty_string(fixture["name"], "name")
    _require_non_empty_string(fixture["scope"], "scope")
    for field in (
        "trace_events",
        "memory_signals",
        "expected_findings",
        "forbidden_findings",
        "forbidden_persisted_text",
    ):
        _require_sequence(fixture[field], field)

    for field in ("expected_findings", "forbidden_findings"):
        _require_finding_assertions(fixture[field], field)
    _require_string_items(fixture["forbidden_persisted_text"], "forbidden_persisted_text")


def load_fixtures(fixture_dir: Path = _FIXTURE_DIR) -> list[dict[str, Any]]:
    """Load and validate reflection report evaluation fixtures."""
    fixtures: list[dict[str, Any]] = []
    for path in sorted(fixture_dir.glob("*.json")):
        fixture = json.loads(path.read_text())
        if not isinstance(fixture, dict):
            raise FixtureValidationError(f"{path.name} must contain a fixture object")
        validate_fixture(fixture)
        fixtures.append(fixture)
    return fixtures


async def run_deterministic_fixture(
    fixture: Mapping[str, Any], tmp_path: Path, monkeypatch: Any
) -> ReflectionEvaluationResult:
    """Run one fixture through run_reflection() with deterministic fake inputs."""
    from fleetent import observability
    from fleetent.intelligence import reflection

    validate_fixture(fixture)
    db_path = tmp_path / "reflection-report-eval.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    trace_events = [_trace_event(event) for event in fixture["trace_events"]]
    memory_signals = [
        _memory_item(memory, str(fixture["scope"])) for memory in fixture["memory_signals"]
    ]
    trace_query_user_ids: list[str | None] = []
    memory_queries: list[tuple[str, str, int]] = []

    def query_trace_events(query: observability.TraceQuery) -> list[observability.TraceEvent]:
        trace_query_user_ids.append(query.user_id)
        return trace_events

    async def search_memory(user_id: str, query: str, *, limit: int) -> list[MemoryItem]:
        memory_queries.append((user_id, query, limit))
        return memory_signals[:limit]

    monkeypatch.setattr(observability, "query_trace_events", query_trace_events)
    monkeypatch.setattr(reflection.memory, "search", search_memory)

    report = await reflection.run_reflection(str(fixture["scope"]))
    persisted_findings_json = _persisted_findings_json(db_path, report.id)
    return ReflectionEvaluationResult(
        fixture=fixture,
        db_path=db_path,
        findings=[
            {
                "type": finding.type,
                "summary": finding.summary,
                "evidence_ids": finding.evidence_ids,
                "metadata": finding.metadata,
            }
            for finding in report.findings
        ],
        persisted_findings_json=persisted_findings_json,
        trace_query_user_ids=trace_query_user_ids,
        memory_queries=memory_queries,
    )


async def run_real_route_smoke(
    fixture: Mapping[str, Any], tmp_path: Path, monkeypatch: Any
) -> ReflectionEvaluationResult:
    """Run a reflection smoke only when explicit local evaluation config is present."""
    if os.environ.get("FLEETENT_EVAL_REAL_REFLECTION") != "1":
        pytest.skip("set FLEETENT_EVAL_REAL_REFLECTION=1 to run real reflection smoke")
    if not os.environ.get("FLEETENT_EVAL_REFLECTION_FIXTURE"):
        pytest.skip("real reflection smoke requires explicit local fixture/config")
    return await run_deterministic_fixture(fixture, tmp_path, monkeypatch)


def assert_finding_expectations(result: ReflectionEvaluationResult) -> None:
    """Assert reflection findings and persisted payload satisfy fixture expectations."""
    for expected in result.fixture["expected_findings"]:
        if not _matching_findings(result.findings, expected):
            raise AssertionError(f"expected finding not found: {expected}")
    for forbidden in result.fixture["forbidden_findings"]:
        matches = _matching_findings(result.findings, forbidden)
        if matches:
            raise AssertionError(f"forbidden finding found: {forbidden}")
    for forbidden_text in result.fixture["forbidden_persisted_text"]:
        if forbidden_text in result.persisted_findings_json:
            raise AssertionError(f"forbidden persisted text found: {forbidden_text}")


def _require_non_empty_string(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise FixtureValidationError(f"{field} must be a non-empty string")


def _require_sequence(value: object, field: str) -> None:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise FixtureValidationError(f"{field} must be a sequence")


def _require_string_items(value: object, field: str) -> None:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise FixtureValidationError(f"{field} must be a sequence")
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise FixtureValidationError(f"{field}[{index}] must be a string")


def _require_finding_assertions(value: object, field: str) -> None:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise FixtureValidationError(f"{field} must be a sequence")
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise FixtureValidationError(f"{field}[{index}] must be an object")
        finding_type = item.get("type")
        if finding_type not in _FINDING_TYPES:
            raise FixtureValidationError(f"{field}[{index}].type is invalid: {finding_type}")
        if "summary_contains" in item:
            _require_non_empty_string(
                item["summary_contains"], f"{field}[{index}].summary_contains"
            )
        if "evidence_ids" in item:
            _require_string_items(item["evidence_ids"], f"{field}[{index}].evidence_ids")
        metadata = item.get("metadata")
        if metadata is not None and not isinstance(metadata, Mapping):
            raise FixtureValidationError(f"{field}[{index}].metadata must be an object")


def _trace_event(event: Mapping[str, Any]) -> Any:
    from fleetent import observability

    return observability.TraceEvent(
        id=str(event.get("id")) if event.get("id") is not None else None,
        run_id=str(event["run_id"]),
        event_type=str(event["event_type"]),
        payload=dict(event.get("payload", {})),
        user_id=str(event["user_id"]) if event.get("user_id") is not None else None,
        agent_id=str(event["agent_id"]) if event.get("agent_id") is not None else None,
        session_id=str(event["session_id"]) if event.get("session_id") is not None else None,
    )


def _memory_item(memory: Mapping[str, Any], user_id: str) -> MemoryItem:
    now = datetime.now(UTC).replace(microsecond=0)
    return MemoryItem(
        id=str(memory["id"]),
        user_id=user_id,
        type=str(memory["type"]),
        content=str(memory["content"]),
        created_at=now,
        updated_at=now,
        expires_at=None,
    )


def _persisted_findings_json(db_path: Path, report_id: str) -> str:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT findings_json
            FROM reflection_reports
            WHERE id = ?
            """,
            (report_id,),
        ).fetchone()
    if row is None:
        raise AssertionError(f"reflection report was not persisted: {report_id}")
    findings_json = row[0]
    if not isinstance(findings_json, str):
        raise AssertionError("persisted findings_json must be a string")
    json.loads(findings_json)
    return findings_json


def _matching_findings(
    findings: Sequence[Mapping[str, Any]], assertion: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    return [finding for finding in findings if _finding_matches(finding, assertion)]


def _finding_matches(finding: Mapping[str, Any], assertion: Mapping[str, Any]) -> bool:
    if finding.get("type") != assertion.get("type"):
        return False
    summary_contains = assertion.get("summary_contains")
    if isinstance(summary_contains, str) and summary_contains not in str(
        finding.get("summary", "")
    ):
        return False
    evidence_ids = assertion.get("evidence_ids")
    if (
        isinstance(evidence_ids, Sequence)
        and not isinstance(evidence_ids, str)
        and list(finding.get("evidence_ids", [])) != list(evidence_ids)
    ):
        return False
    metadata = assertion.get("metadata")
    if isinstance(metadata, Mapping):
        finding_metadata = finding.get("metadata", {})
        if not isinstance(finding_metadata, Mapping):
            return False
        for key, value in metadata.items():
            if finding_metadata.get(key) != value:
                return False
    return True
