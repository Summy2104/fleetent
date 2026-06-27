from __future__ import annotations

import json
from pathlib import Path


def test_owner_capability_contract_evidence_covers_all_pilot_domains(tmp_path):
    from fleetent.observability.pilot_verification import (
        CapabilityEvidence,
        PilotVerificationReport,
        render_json_report,
        render_markdown_report,
    )

    evidence = [
        CapabilityEvidence(
            capability="Observability",
            status="passed",
            command="uv run pytest tests/integration/test_trace_events.py -q",
            artifacts=[Path("tests/integration/test_trace_events.py")],
            notes=["trace query, usage/performance summary, diagnostics redaction/export"],
        ),
        CapabilityEvidence(
            capability="Memory",
            status="passed",
            command="uv run pytest tests/integration/test_shared_memory.py -q",
            artifacts=[Path("tests/integration/test_facts_extract_conflict_retract.py")],
            notes=["item lifecycle, retention/compaction, tenant/team isolation"],
        ),
        CapabilityEvidence(
            capability="Long-term Context",
            status="passed",
            command="uv run pytest tests/integration/test_long_term_context_runtime.py -q",
            artifacts=[Path("tests/integration/test_long_term_ctx.py")],
            notes=["source attribution, budget decisions, memory + knowledge assembly"],
        ),
        CapabilityEvidence(
            capability="Reflection",
            status="passed",
            command="uv run pytest tests/integration/test_reflection.py -q",
            artifacts=[Path("tests/integration/test_kb_reflection_reports.py")],
            notes=["report generation, proposal lifecycle, trend aggregation"],
        ),
        CapabilityEvidence(
            capability="Vector Store",
            status="passed",
            command="uv run pytest tests/integration/test_vector_store_reindex.py -q",
            artifacts=[Path("tests/integration/test_rerank_providers.py")],
            notes=["namespace isolation, reindex, deterministic provider behavior"],
        ),
        CapabilityEvidence(
            capability="Knowledge Base",
            status="passed",
            command="uv run pytest tests/integration/test_knowledge_base_sync_planner.py -q",
            artifacts=[Path("tests/integration/test_knowledge_connector_operations.py")],
            notes=["local ingest, parser dispatch, fake connector, search planner evidence"],
        ),
        CapabilityEvidence(
            capability="Deployment / Config",
            status="passed",
            command="uv run pytest tests/integration/test_deployment_docs.py -q",
            artifacts=[Path("tests/integration/test_upgrade_script.py")],
            notes=["config fail-fast, upgrade/backup dry-run, diagnostics boundaries"],
        ),
    ]
    report = PilotVerificationReport.for_current_run(
        command_results=[],
        capability_evidence=evidence,
        real_smoke=[],
        issues=[],
        artifact_dir=tmp_path,
    )

    markdown = render_markdown_report(report)
    payload = json.loads(render_json_report(report))

    expected = {
        "Observability",
        "Memory",
        "Long-term Context",
        "Reflection",
        "Vector Store",
        "Knowledge Base",
        "Deployment / Config",
    }
    assert {item["capability"] for item in payload["capability_evidence"]} == expected
    for capability in expected:
        assert f"### {capability}" in markdown
    assert payload["recommendation"] == "Go"


def test_owner_capability_evidence_rejects_missing_or_external_artifacts():
    from fleetent.observability.pilot_verification import CapabilityEvidence

    missing = Path("tests/integration/does_not_exist.py")

    try:
        CapabilityEvidence(
            capability="Observability",
            status="passed",
            command="uv run pytest tests/integration -x -q",
            artifacts=[missing],
            notes=[],
        )
    except ValueError as exc:
        assert str(missing) in str(exc)
    else:
        raise AssertionError("missing artifact was accepted")
