from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime

from fleetent.config import DiagnosticsSettings, Settings


def test_export_diagnostics_creates_zip_with_manifest(tmp_path):
    from fleetent.observability.diagnostics import DiagnosticsExportRequest, export_diagnostics

    package = export_diagnostics(
        DiagnosticsExportRequest(output_dir=tmp_path, include_logs=False, include_traces=False)
    )

    assert package.path.exists()
    with zipfile.ZipFile(package.path) as archive:
        assert "manifest.json" in archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["redaction_version"] == 1


def test_export_diagnostics_includes_sanitized_logs(tmp_path):
    from fleetent.observability.diagnostics import DiagnosticsExportRequest, export_diagnostics

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "2026-06-02.log").write_text(
        "token secret-value user@example.com 13800138000\n",
        encoding="utf-8",
    )

    package = export_diagnostics(
        DiagnosticsExportRequest(
            output_dir=tmp_path / "exports",
            log_dir=log_dir,
            include_traces=False,
        )
    )

    with zipfile.ZipFile(package.path) as archive:
        exported = archive.read("logs/2026-06-02.log").decode()

    assert "secret-value" not in exported
    assert "user@example.com" not in exported
    assert "13800138000" not in exported


def test_export_diagnostics_includes_trace_and_summaries(monkeypatch, tmp_path):
    from fleetent.observability import diagnostics
    from fleetent.observability.diagnostics import DiagnosticsExportRequest, export_diagnostics
    from fleetent.observability.traces import TraceEvent

    monkeypatch.setattr(
        diagnostics,
        "query_trace_events",
        lambda query: iter(
            [
                TraceEvent(
                    run_id="run-1",
                    event_type="tool_call_completed",
                    payload={"text": "x" * 3000, "token": "secret-value"},
                    ts=datetime(2026, 6, 2, tzinfo=UTC),
                )
            ]
        ),
    )

    package = export_diagnostics(DiagnosticsExportRequest(output_dir=tmp_path, include_logs=False))

    with zipfile.ZipFile(package.path) as archive:
        names = set(archive.namelist())
        events = archive.read("traces/events.jsonl").decode()

    assert {
        "traces/events.jsonl",
        "traces/usage_summary.json",
        "traces/performance_summary.json",
    } <= names
    assert "secret-value" not in events
    assert "truncated" in events


def test_export_diagnostics_includes_connector_environment_and_config(monkeypatch, tmp_path):
    from fleetent.observability import diagnostics
    from fleetent.observability.diagnostics import DiagnosticsExportRequest, export_diagnostics

    monkeypatch.setattr(
        diagnostics,
        "list_configured_connectors",
        lambda settings=None: [
            {
                "connector_id": "eng-drive",
                "connector_type": "google_drive",
                "credential_ref": "file:///secret/path/google.json",
                "token": "secret-value",
            }
        ],
    )

    package = export_diagnostics(
        DiagnosticsExportRequest(
            output_dir=tmp_path,
            include_logs=False,
            include_traces=False,
            settings=Settings(
                anthropic_api_key="test-key",
                diagnostics=DiagnosticsSettings(export_dir=str(tmp_path)),
            ),
        )
    )

    with zipfile.ZipFile(package.path) as archive:
        connector_status = archive.read("knowledge_connectors/status.json").decode()
        environment = json.loads(archive.read("environment.json"))
        config = json.loads(archive.read("config_summary.json"))

    assert "secret-value" not in connector_status
    assert "google.json" in connector_status
    assert "python_version" in environment
    assert config["diagnostics"]["retention_enabled"] is False


def test_export_diagnostics_includes_latest_connector_status(monkeypatch, tmp_path):
    from fleetent.intelligence.knowledge_base.operations import (
        ConnectorStatus,
        ConnectorSummary,
    )
    from fleetent.observability import diagnostics
    from fleetent.observability.diagnostics import DiagnosticsExportRequest, export_diagnostics

    monkeypatch.setattr(
        diagnostics,
        "list_configured_connectors",
        lambda settings=None: [
            ConnectorSummary(
                connector_id="eng-drive",
                connector_type="google_drive",
                enabled=True,
                tenant_id="default",
                kb_id="engineering",
                scope="folder:folder-1",
                credential_ref_summary="file:google.json",
            )
        ],
    )
    monkeypatch.setattr(
        diagnostics,
        "get_connector_status",
        lambda connector_id, settings=None: ConnectorStatus(
            connector_id=connector_id,
            connector_type="google_drive",
            tenant_id="default",
            kb_id="engineering",
            last_status="sync_failed",
            last_started_at=None,
            last_finished_at=None,
            last_summary={"failed": 1, "token": "secret-value"},
            last_error="credential secret-value failed",
        ),
    )

    package = export_diagnostics(
        DiagnosticsExportRequest(
            output_dir=tmp_path,
            include_logs=False,
            include_traces=False,
            settings=Settings(anthropic_api_key="test-key"),
        )
    )

    with zipfile.ZipFile(package.path) as archive:
        connector_status = archive.read("knowledge_connectors/status.json").decode()

    assert "sync_failed" in connector_status
    assert "failed" in connector_status
    assert "secret-value" not in connector_status


def test_export_diagnostics_excludes_business_data_and_database_files(tmp_path):
    from fleetent.observability.diagnostics import DiagnosticsExportRequest, export_diagnostics

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "fleetent.db").write_text("sqlite main db memory KB document body")
    backup_dir = data_dir / "backups" / "20260602-000000"
    backup_dir.mkdir(parents=True)
    (backup_dir / "fleetent.db").write_text("backup db")

    package = export_diagnostics(
        DiagnosticsExportRequest(
            output_dir=tmp_path / "exports",
            data_dir=data_dir,
            include_logs=False,
            include_traces=False,
        )
    )

    with zipfile.ZipFile(package.path) as archive:
        names = archive.namelist()
        combined = "\n".join(
            archive.read(name).decode(errors="ignore") for name in names if name.endswith(".json")
        )

    assert all(not name.endswith("fleetent.db") for name in names)
    assert "memory KB document body" not in combined


def test_export_records_status_unavailable_when_status_lookup_raises(monkeypatch, tmp_path):
    from fleetent.intelligence.knowledge_base.operations import ConnectorSummary
    from fleetent.observability import diagnostics
    from fleetent.observability.diagnostics import DiagnosticsExportRequest, export_diagnostics

    monkeypatch.setattr(
        diagnostics,
        "list_configured_connectors",
        lambda settings=None: [
            ConnectorSummary(
                connector_id="eng-drive",
                connector_type="google_drive",
                enabled=True,
                tenant_id="default",
                kb_id="engineering",
                scope="folder:folder-1",
                credential_ref_summary="file:google.json",
            )
        ],
    )

    def boom(connector_id, settings=None):
        raise RuntimeError("status backend down")

    monkeypatch.setattr(diagnostics, "get_connector_status", boom)

    package = export_diagnostics(
        DiagnosticsExportRequest(
            output_dir=tmp_path,
            include_logs=False,
            include_traces=False,
            settings=Settings(anthropic_api_key="test-key"),
        )
    )

    with zipfile.ZipFile(package.path) as archive:
        status = archive.read("knowledge_connectors/status.json").decode()

    assert "status_unavailable" in status
    assert "status backend down" in status


def test_get_connector_status_delegates_to_operations(monkeypatch):
    from fleetent.intelligence.knowledge_base import operations
    from fleetent.observability import diagnostics

    monkeypatch.setattr(
        operations, "get_connector_status", lambda connector_id, settings=None: {"id": connector_id}
    )

    assert diagnostics.get_connector_status("eng-drive") == {"id": "eng-drive"}


def test_list_configured_connectors_delegates_to_operations(monkeypatch):
    from fleetent.intelligence.knowledge_base import operations
    from fleetent.observability import diagnostics

    monkeypatch.setattr(
        operations, "list_configured_connectors", lambda settings=None: ["c1", "c2"]
    )

    assert diagnostics.list_configured_connectors() == ["c1", "c2"]


def test_export_skips_secret_files_in_manifest(tmp_path):
    from fleetent.observability.diagnostics import DiagnosticsExportRequest, export_diagnostics

    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "google.json").write_text("token")

    package = export_diagnostics(
        DiagnosticsExportRequest(
            output_dir=tmp_path / "exports",
            secrets_dir=secrets_dir,
            include_logs=False,
            include_traces=False,
        )
    )

    with zipfile.ZipFile(package.path) as archive:
        manifest = json.loads(archive.read("manifest.json"))

    skipped = {entry["name"] for entry in manifest["skipped_artifacts"]}
    assert "secrets/google.json" in skipped


def test_diagnostics_database_factory_builds_sqlite_database():
    from fleetent.db import SQLiteDatabase
    from fleetent.observability import diagnostics

    assert isinstance(diagnostics._database(), SQLiteDatabase)
