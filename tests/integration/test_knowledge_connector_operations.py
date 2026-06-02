from __future__ import annotations

import json

from fleetent.config import Settings
from fleetent.db import create_database
from tests.integration.test_migrations import apply_migrations


def _patch_operations_database(monkeypatch, tmp_path):
    from fleetent.intelligence.knowledge_base import operations

    db_path = tmp_path / "connectors.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(operations, "_database", lambda: database)
    return database


def _settings(**knowledge_base: object) -> Settings:
    return Settings(anthropic_api_key="test-key", knowledge_base=knowledge_base)


def test_never_run_connector_status_is_stable(monkeypatch, tmp_path):
    _patch_operations_database(monkeypatch, tmp_path)
    from fleetent.intelligence.knowledge_base import get_connector_status

    settings = _settings(
        google_drive={
            "connectors": [
                {
                    "connector_id": "eng-drive",
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "folder_id": "folder-1",
                    "credential_ref": "file:///secure/google.json",
                }
            ]
        }
    )

    status = get_connector_status("eng-drive", settings=settings)

    assert status.last_status == "never_run"
    assert status.last_summary == {}
    assert status.last_error is None


def test_connector_status_overwrites_previous_status(monkeypatch, tmp_path):
    _patch_operations_database(monkeypatch, tmp_path)
    from fleetent.intelligence.knowledge_base import operations

    operations.record_connector_status(
        connector_id="eng-drive",
        connector_type="google_drive",
        tenant_id="default",
        kb_id="engineering",
        status="dry_run_ok",
        summary={"planned": 1},
        error=None,
    )
    operations.record_connector_status(
        connector_id="eng-drive",
        connector_type="google_drive",
        tenant_id="default",
        kb_id="engineering",
        status="sync_succeeded",
        summary={"planned": 2},
        error=None,
    )

    row = (
        operations._database()
        .execute("SELECT last_status, last_summary_json FROM knowledge_connector_status")
        .fetchone()
    )

    assert row is not None
    assert row["last_status"] == "sync_succeeded"
    assert json.loads(row["last_summary_json"]) == {"planned": 2}


def test_connector_status_redacts_summary_and_error(monkeypatch, tmp_path):
    _patch_operations_database(monkeypatch, tmp_path)
    from fleetent.intelligence.knowledge_base import operations

    operations.record_connector_status(
        connector_id="eng-drive",
        connector_type="google_drive",
        tenant_id="default",
        kb_id="engineering",
        status="sync_failed",
        summary={"token": "secret-token", "failed": 1},
        error="credential secret-token failed",
    )

    row = (
        operations._database()
        .execute("SELECT last_summary_json, last_error FROM knowledge_connector_status")
        .fetchone()
    )

    assert row is not None
    assert "secret-token" not in row["last_summary_json"]
    assert "secret-token" not in row["last_error"]


async def test_dry_run_records_status_without_mutating_knowledge(monkeypatch, tmp_path):
    database = _patch_operations_database(monkeypatch, tmp_path)
    from fleetent.intelligence.knowledge_base import run_connector_sync
    from fleetent.intelligence.knowledge_base.connectors.google_drive import (
        FakeGoogleDriveClient,
        GoogleDriveFile,
    )

    settings = _settings(
        google_drive={
            "connectors": [
                {
                    "connector_id": "eng-drive",
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "folder_id": "folder-1",
                    "credential_ref": "file:///secure/google.json",
                }
            ]
        }
    )
    client = FakeGoogleDriveClient(
        files_by_folder={
            "folder-1": [
                GoogleDriveFile(
                    id="file-1",
                    name="guide.txt",
                    mime_type="text/plain",
                    modified_time="2026-06-02T00:00:00Z",
                )
            ]
        }
    )

    result = await run_connector_sync(
        "eng-drive",
        settings=settings,
        dry_run=True,
        google_drive_client=client,
    )

    assert result.status == "dry_run_ok"
    assert result.summary["planned"] == 1
    assert database.execute("SELECT id FROM knowledge_documents").fetchall() == []
    status = database.execute("SELECT last_status FROM knowledge_connector_status").fetchone()
    assert status == {"last_status": "dry_run_ok"}


async def test_sync_records_success_status(monkeypatch, tmp_path):
    database = _patch_operations_database(monkeypatch, tmp_path)
    from fleetent.intelligence.knowledge_base import run_connector_sync
    from fleetent.intelligence.knowledge_base.connectors.google_drive import FakeGoogleDriveClient

    settings = _settings(
        google_drive={
            "connectors": [
                {
                    "connector_id": "eng-drive",
                    "tenant_id": "default",
                    "kb_id": "engineering",
                    "folder_id": "folder-1",
                    "credential_ref": "file:///secure/google.json",
                }
            ]
        }
    )

    result = await run_connector_sync(
        "eng-drive",
        settings=settings,
        dry_run=False,
        google_drive_client=FakeGoogleDriveClient(files_by_folder={"folder-1": []}),
    )

    assert result.status == "sync_succeeded"
    status = database.execute("SELECT last_status FROM knowledge_connector_status").fetchone()
    assert status == {"last_status": "sync_succeeded"}
