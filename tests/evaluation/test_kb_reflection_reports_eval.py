import json
from pathlib import Path
from types import SimpleNamespace

FIXTURE = Path("tests/evaluation/fixtures/kb_reflection_reports/basic.json")


async def test_kb_reflection_evaluation_fixture_validates_expected_and_forbidden_findings(
    monkeypatch,
):
    from fleetent.intelligence import reflection

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    events = [
        SimpleNamespace(
            id=item["id"],
            run_id=item["run_id"],
            event_type=item["event_type"],
            payload=item["payload"],
        )
        for item in payload["events"]
    ]

    monkeypatch.setattr(reflection.observability, "query_trace_events", lambda query: events)
    monkeypatch.setattr(
        reflection.knowledge_base,
        "list_configured_connectors",
        lambda: [
            SimpleNamespace(connector_id=item["connector_id"]) for item in payload["connectors"]
        ],
    )
    monkeypatch.setattr(
        reflection.knowledge_base,
        "get_connector_status",
        lambda connector_id: SimpleNamespace(
            **next(
                item
                for item in payload["connector_statuses"]
                if item["connector_id"] == connector_id
            )
        ),
    )
    monkeypatch.setattr(reflection, "_save_kb_reflection_report", lambda report: None)

    report = await reflection.run_kb_reflection_report(payload["scope"])
    finding_types = {finding.type for finding in report.findings}
    persisted_payload = reflection._kb_findings_json(report.findings)

    assert set(payload["expected_findings"]) <= finding_types
    assert finding_types.isdisjoint(payload["forbidden_findings"])
    assert payload["forbidden_raw_text"] not in persisted_payload
