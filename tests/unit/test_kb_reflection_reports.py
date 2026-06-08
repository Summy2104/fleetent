from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock


def test_kb_reflection_public_api_is_importable():
    from fleetent.reflection import (
        KnowledgeBaseReflectionFinding,
        KnowledgeBaseReflectionReport,
        run_kb_reflection_report,
    )

    assert KnowledgeBaseReflectionFinding is not None
    assert KnowledgeBaseReflectionReport is not None
    assert run_kb_reflection_report is not None


async def test_kb_reflection_uses_observability_and_kb_public_apis(monkeypatch):
    from fleetent import reflection

    trace_calls = []
    connector_calls = []

    def query_trace_events(query):
        trace_calls.append(query)
        return [
            SimpleNamespace(
                id="trace-1",
                event_type="kb_retrieval",
                payload={"query": "missing topic", "result_count": 0},
            )
        ]

    def list_connectors():
        connector_calls.append("list")
        return [SimpleNamespace(connector_id="drive-main")]

    def get_status(connector_id: str):
        connector_calls.append(connector_id)
        return SimpleNamespace(
            connector_id=connector_id,
            status="failed",
            last_sync_at=datetime.now(UTC),
            error_summary="sync failed",
        )

    monkeypatch.setattr(reflection.observability, "query_trace_events", query_trace_events)
    monkeypatch.setattr(reflection.knowledge_base, "list_configured_connectors", list_connectors)
    monkeypatch.setattr(reflection.knowledge_base, "get_connector_status", get_status)
    monkeypatch.setattr(reflection, "_save_kb_reflection_report", lambda report: None)

    report = await reflection.run_kb_reflection_report("tenant-a")

    assert trace_calls
    assert connector_calls == ["list", "drive-main"]
    assert {finding.type for finding in report.findings} >= {
        "missing_knowledge",
        "connector_sync_issue",
    }


async def test_kb_reflection_generates_quality_and_graph_gap_findings(monkeypatch):
    from fleetent import reflection

    events = [
        SimpleNamespace(
            id="trace-low",
            event_type="kb_retrieval",
            payload={
                "query": "cache reset",
                "top_score": 0.12,
                "source_attribution_count": 0,
            },
        ),
        SimpleNamespace(
            id="trace-graph",
            event_type="kb_retrieval",
            payload={
                "query": "Which service depends on Billing API?",
                "graph_result_count": 0,
                "graph_evidence_count": 0,
            },
        ),
        SimpleNamespace(
            id="trace-stale",
            event_type="kb_retrieval",
            payload={
                "query": "old policy",
                "stale_document_id": "doc-old",
            },
        ),
    ]

    monkeypatch.setattr(reflection.observability, "query_trace_events", lambda query: events)
    monkeypatch.setattr(reflection.knowledge_base, "list_configured_connectors", lambda: [])
    monkeypatch.setattr(reflection.knowledge_base, "get_connector_status", AsyncMock())
    monkeypatch.setattr(reflection, "_save_kb_reflection_report", lambda report: None)

    report = await reflection.run_kb_reflection_report("tenant-a")

    assert {finding.type for finding in report.findings} == {
        "low_retrieval_quality",
        "entity_graph_gap",
        "stale_document",
    }
    for finding in report.findings:
        assert finding.evidence_refs
        assert finding.recommendation
        assert finding.affected_resource
