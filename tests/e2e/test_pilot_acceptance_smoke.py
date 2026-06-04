from __future__ import annotations

import json


def test_pilot_acceptance_smoke_report_captures_local_kb_memory_trace_and_connector_paths(
    tmp_path,
):
    from fleetent.observability.pilot_verification import (
        PilotSmokeScenario,
        write_pilot_smoke_artifact,
    )

    scenarios = [
        PilotSmokeScenario(
            name="local KB agent query",
            evidence={
                "query": "How do I install Fleetent?",
                "answer": "Use the pilot install checklist.",
                "sources": [{"source_id": "pilot-install-checklist.md", "kb_id": "engineering"}],
            },
            required_evidence_keys=["query", "answer", "sources"],
        ),
        PilotSmokeScenario(
            name="memory proposal apply",
            evidence={
                "proposal_id": "proposal-1",
                "approved_memory": "Team prefers short release notes.",
                "later_context_sources": [{"source_type": "memory", "source_id": "mem-1"}],
            },
            required_evidence_keys=["proposal_id", "approved_memory", "later_context_sources"],
        ),
        PilotSmokeScenario(
            name="agent observability",
            evidence={
                "run_id": "run-1",
                "trace_events": ["agent_run_started", "agent_run_completed"],
                "usage": {"total_tokens": 42},
                "performance": {"completed_runs": 1},
            },
            required_evidence_keys=["run_id", "trace_events", "usage", "performance"],
        ),
        PilotSmokeScenario(
            name="fake connector sync",
            evidence={
                "check": "ok",
                "dry_run": {"planned": 1},
                "sync": {"status": "sync_succeeded"},
                "latest_status": "sync_succeeded",
            },
            required_evidence_keys=["check", "dry_run", "sync", "latest_status"],
        ),
    ]

    artifact = write_pilot_smoke_artifact(tmp_path / "pilot-smoke.json", scenarios)

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert [item["name"] for item in payload["scenarios"]] == [
        "local KB agent query",
        "memory proposal apply",
        "agent observability",
        "fake connector sync",
    ]
    assert payload["scenarios"][0]["evidence"]["sources"][0]["source_id"].endswith(".md")
    assert payload["status"] == "passed"


def test_pilot_acceptance_smoke_rejects_missing_human_evidence(tmp_path):
    from fleetent.observability.pilot_verification import (
        PilotSmokeScenario,
        write_pilot_smoke_artifact,
    )

    scenario = PilotSmokeScenario(
        name="local KB agent query",
        evidence={"query": "How do I install Fleetent?"},
        required_evidence_keys=["query", "answer", "sources"],
    )

    try:
        write_pilot_smoke_artifact(tmp_path / "pilot-smoke.json", [scenario])
    except ValueError as exc:
        assert "answer" in str(exc)
        assert "sources" in str(exc)
    else:
        raise AssertionError("incomplete Pilot smoke evidence was accepted")


def test_real_provider_smoke_gates_skip_without_flags_or_credentials(monkeypatch):
    from fleetent.observability.pilot_verification import real_smoke_gate

    monkeypatch.delenv("FLEETENT_REAL_LLM_SMOKE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    smoke = real_smoke_gate(
        name="real LLM",
        flag="FLEETENT_REAL_LLM_SMOKE",
        credential_env=["ANTHROPIC_API_KEY"],
    )

    assert smoke.status == "skipped"
    assert smoke.skip_reason == "missing FLEETENT_REAL_LLM_SMOKE, ANTHROPIC_API_KEY"


def test_real_saas_smoke_gates_name_missing_credential_refs(monkeypatch):
    from fleetent.observability.pilot_verification import real_smoke_gate

    monkeypatch.setenv("FLEETENT_GOOGLE_DRIVE_SMOKE", "1")
    monkeypatch.delenv("FLEETENT_GOOGLE_DRIVE_CREDENTIAL_REF", raising=False)
    monkeypatch.delenv("FLEETENT_GOOGLE_DRIVE_FOLDER_ID", raising=False)

    smoke = real_smoke_gate(
        name="Google Drive",
        flag="FLEETENT_GOOGLE_DRIVE_SMOKE",
        credential_env=[
            "FLEETENT_GOOGLE_DRIVE_CREDENTIAL_REF",
            "FLEETENT_GOOGLE_DRIVE_FOLDER_ID",
        ],
    )

    assert smoke.status == "skipped"
    assert smoke.skip_reason == (
        "missing FLEETENT_GOOGLE_DRIVE_CREDENTIAL_REF, FLEETENT_GOOGLE_DRIVE_FOLDER_ID"
    )
