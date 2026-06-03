import json
import zipfile


def test_diagnostics_manifest_records_artifacts_and_skips_forbidden_files(tmp_path):
    from fleetent.observability.diagnostics import DiagnosticsExportRequest, export_diagnostics

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "fleetent.db").write_text("sqlite secret", encoding="utf-8")
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir()
    (secret_dir / "token.txt").write_text("secret-token", encoding="utf-8")

    package = export_diagnostics(
        DiagnosticsExportRequest(
            output_dir=tmp_path / "exports",
            data_dir=data_dir,
            secrets_dir=secret_dir,
            include_logs=False,
            include_traces=False,
            include_connector_status=False,
        )
    )

    with zipfile.ZipFile(package.path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        joined = "\n".join(names)

    assert "data/fleetent.db" not in joined
    assert "secrets/token.txt" not in joined
    skipped = {item["name"]: item["reason"] for item in manifest["skipped_artifacts"]}
    assert skipped["data/fleetent.db"] == "sqlite database excluded"
    assert skipped["secrets/token.txt"] == "secret file excluded"
    assert any(item["name"] == "config_summary.json" for item in manifest["artifacts"])


def test_pilot_gate_command_result_includes_duration_required_and_artifact(tmp_path):
    from fleetent.observability.pilot_verification import GateCommandResult

    result = GateCommandResult(
        command="uv run pytest -x -q",
        status="passed",
        required=True,
        duration_seconds=1.25,
        artifact=tmp_path / "pytest.txt",
    )

    payload = result.to_json()
    assert payload["required"] is True
    assert payload["duration_seconds"] == 1.25
    assert payload["artifact"].endswith("pytest.txt")


def test_pilot_report_includes_config_diagnostics_and_connector_evidence(tmp_path):
    from fleetent.observability.pilot_verification import (
        ConfigValidationEvidence,
        DiagnosticsEvidence,
        PilotVerificationReport,
        RealSmokeEvidence,
    )

    report = PilotVerificationReport.for_current_run(
        command_results=[],
        capability_evidence=[],
        real_smoke=[
            RealSmokeEvidence(name="google_drive", status="skipped", summary="missing opt-in")
        ],
        issues=[],
        artifact_dir=tmp_path,
        config_validation=ConfigValidationEvidence(status="pass", error_count=0, skipped_count=1),
        diagnostics=DiagnosticsEvidence(manifest_path=tmp_path / "manifest.json", artifact_count=3),
        connector_status=[{"connector_id": "gdrive", "last_status": "dry_run_ok"}],
    )

    payload = report.to_json()
    assert payload["config_validation"]["status"] == "pass"
    assert payload["diagnostics"]["artifact_count"] == 3
    assert payload["connector_status"][0]["connector_id"] == "gdrive"


def test_real_connector_execute_requires_execute_opt_in_and_pilot_fixture():
    from fleetent.intelligence.knowledge_base.operations import real_connector_smoke_gate

    skipped = real_connector_smoke_gate(
        connector_id="gdrive",
        smoke_enabled=True,
        credential_ref="env:GDRIVE_TOKEN",
        execute_sync=True,
        execute_enabled=False,
        pilot_fixture=False,
    )

    assert skipped.execute_sync.status == "skipped"
    assert "execute opt-in" in skipped.execute_sync.skipped_reason

    not_fixture = real_connector_smoke_gate(
        connector_id="gdrive",
        smoke_enabled=True,
        credential_ref="env:GDRIVE_TOKEN",
        execute_sync=True,
        execute_enabled=True,
        pilot_fixture=False,
    )
    assert "Pilot fixture" in not_fixture.execute_sync.skipped_reason
