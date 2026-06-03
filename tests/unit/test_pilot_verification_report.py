from __future__ import annotations

import json
from pathlib import Path


def test_report_writer_emits_markdown_and_json_with_required_sections(tmp_path):
    from scripts.generate_pilot_verification_report import write_fixture_report

    outputs = write_fixture_report(tmp_path)

    assert outputs.markdown_path.exists()
    assert outputs.json_path.exists()
    markdown = outputs.markdown_path.read_text(encoding="utf-8")
    payload = json.loads(outputs.json_path.read_text(encoding="utf-8"))

    assert "## Run Metadata" in markdown
    assert "## Automated Checks" in markdown
    assert "## Capability Evidence" in markdown
    assert "## Real Smoke Evidence" in markdown
    assert "## Issues" in markdown
    assert "## Final Recommendation" in markdown
    assert payload["metadata"]["git_sha"]
    assert payload["metadata"]["python_version"]
    assert payload["command_results"]
    assert {item["capability"] for item in payload["capability_evidence"]} == {
        "Observability",
        "Memory",
        "Long-term Context",
        "Reflection",
        "Vector Store",
        "Knowledge Base",
        "Deployment / Config",
    }
    assert {item["name"] for item in payload["real_smoke"]} == {
        "real LLM",
        "real embedding",
        "real rerank",
        "Google Drive",
        "Confluence",
        "Docker Compose",
    }


def test_report_recommendation_rules_map_pilot_impact():
    from fleetent.observability.pilot_verification import (
        CapabilityEvidence,
        CommandResult,
        classify_issue,
        recommend,
    )

    evidence = [
        CapabilityEvidence(
            capability="Observability",
            status="passed",
            command="uv run pytest tests/integration/test_trace_events.py -q",
            artifacts=[Path("tests/integration/test_trace_events.py")],
        )
    ]

    assert (
        recommend(
            [CommandResult("uv run pytest -x -q", "passed", exit_code=0)],
            evidence,
            [],
            [classify_issue(source="docs", title="Pilot runbook missing report command")],
        )
        == "Conditional Go"
    )
    assert (
        recommend(
            [CommandResult("uv run pytest -x -q", "failed", exit_code=1)],
            evidence,
            [],
            [],
        )
        == "No-Go"
    )
    assert (
        classify_issue(source="pytest", title="capability contract failed").classification
        == "Pilot blocker"
    )
