import json
from types import SimpleNamespace

from fleetent.db import create_database
from tests.integration.test_migrations import apply_migrations


async def test_run_kb_reflection_report_persists_redacted_payload(tmp_path, monkeypatch):
    from fleetent import reflection

    db_path = tmp_path / "reflection-kb.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    raw_transcript = "USER SECRET FULL TRANSCRIPT SHOULD NOT BE STORED"

    monkeypatch.setattr(reflection, "_database", lambda: database)
    monkeypatch.setattr(
        reflection.observability,
        "query_trace_events",
        lambda query: [
            SimpleNamespace(
                id="trace-1",
                run_id="run-1",
                event_type="kb_retrieval",
                payload={
                    "query": "missing runbook",
                    "result_count": 0,
                    "transcript": raw_transcript,
                    "document_body": "FULL DOCUMENT BODY SHOULD NOT BE STORED",
                },
            )
        ],
    )
    monkeypatch.setattr(reflection.knowledge_base, "list_configured_connectors", lambda: [])

    report = await reflection.run_kb_reflection_report("tenant-a")

    row = database.execute(
        """
        SELECT findings_json, signal_summary_json
        FROM kb_reflection_reports
        WHERE id = :id
        """,
        {"id": report.id},
    ).fetchone()

    assert row is not None
    persisted = row["findings_json"] + row["signal_summary_json"]
    assert "missing_knowledge" in persisted
    assert "trace-1" in persisted
    assert raw_transcript not in persisted
    assert "FULL DOCUMENT BODY" not in persisted
    assert json.loads(row["signal_summary_json"])["finding_count"] == 1


async def test_run_kb_reflection_report_returns_insufficient_signal_when_kb_unavailable(
    monkeypatch,
):
    from fleetent import reflection

    monkeypatch.setattr(reflection.observability, "query_trace_events", lambda query: [])
    monkeypatch.setattr(
        reflection.knowledge_base,
        "list_configured_connectors",
        lambda: (_ for _ in ()).throw(RuntimeError("kb unavailable")),
    )
    monkeypatch.setattr(reflection, "_save_kb_reflection_report", lambda report: None)

    report = await reflection.run_kb_reflection_report("tenant-a")

    assert [finding.type for finding in report.findings] == ["insufficient_signal"]
    assert report.signal_summary["finding_count"] == 1
