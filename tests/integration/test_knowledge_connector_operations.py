from __future__ import annotations

import json

import pytest

from fleetent.db import SQLiteDatabase, create_database
from fleetent.knowledge_base.config import KnowledgeConfigSnapshot
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.schema_migrations import migrate


def _patch_operations_database(monkeypatch, tmp_path):
    from fleetent.knowledge_base import runtime

    db_path = tmp_path / "connectors.db"
    migrate(SQLiteDatabase(path=db_path), KB_MIGRATIONS)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(runtime, "_kb_db", database)
    monkeypatch.setattr(runtime, "_kb_vector_backend", None)
    return database


def _settings(**knowledge_base: object) -> KnowledgeConfigSnapshot:
    knowledge_bases: list[dict[str, object]] = []
    for source_type, block in knowledge_base.items():
        connectors = block.get("connectors", [])  # type: ignore[union-attr]
        for item in connectors:  # type: ignore[union-attr]
            source = dict(item)
            source["id"] = source.pop("connector_id")
            source["type"] = source_type
            tenant_id = str(source.pop("tenant_id"))
            kb_id = str(source.pop("kb_id"))
            knowledge_bases.append(
                {
                    "id": kb_id,
                    "tenant_id": tenant_id,
                    "sources": [source],
                }
            )
    return KnowledgeConfigSnapshot.model_validate({"knowledge_bases": knowledge_bases})


def test_never_run_connector_status_is_stable(monkeypatch, tmp_path):
    _patch_operations_database(monkeypatch, tmp_path)
    from fleetent.knowledge_base import get_connector_status

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
    database = _patch_operations_database(monkeypatch, tmp_path)
    from fleetent.knowledge_base import operations

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

    row = database.execute(
        "SELECT last_status, last_summary_json FROM knowledge_connector_status"
    ).fetchone()

    assert row is not None
    assert row["last_status"] == "sync_succeeded"
    assert json.loads(row["last_summary_json"]) == {"planned": 2}


def test_connector_status_redacts_summary_and_error(monkeypatch, tmp_path):
    database = _patch_operations_database(monkeypatch, tmp_path)
    from fleetent.knowledge_base import operations

    operations.record_connector_status(
        connector_id="eng-drive",
        connector_type="google_drive",
        tenant_id="default",
        kb_id="engineering",
        status="sync_failed",
        summary={"token": "secret-token", "failed": 1},
        error="credential secret-token failed",
    )

    row = database.execute(
        "SELECT last_summary_json, last_error FROM knowledge_connector_status"
    ).fetchone()

    assert row is not None
    assert "secret-token" not in row["last_summary_json"]
    assert "secret-token" not in row["last_error"]


async def test_dry_run_records_status_without_mutating_knowledge(monkeypatch, tmp_path):
    database = _patch_operations_database(monkeypatch, tmp_path)
    from fleetent.knowledge_base import run_connector_sync
    from fleetent.knowledge_base.connectors.google_drive import (
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
    from fleetent.knowledge_base import run_connector_sync
    from fleetent.knowledge_base.connectors.google_drive import FakeGoogleDriveClient

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


def test_explicit_connector_settings_override_platform_yaml(monkeypatch, tmp_path):
    from fleetent.knowledge_base import get_connector_config, list_configured_connectors

    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    (tmp_path / "platform.yaml").write_text(
        """
knowledge:
  knowledge_bases:
    - id: yaml-kb
      tenant_id: default
      sources:
        - id: yaml-drive
          type: google_drive
          folder_id: yaml-folder
          credential_ref: file:///secure/yaml.json
""",
        encoding="utf-8",
    )
    settings = _settings(
        google_drive={
            "connectors": [
                {
                    "connector_id": "db-drive",
                    "tenant_id": "tenant-a",
                    "kb_id": "db-kb",
                    "folder_id": "db-folder",
                    "credential_ref": "file:///secure/db.json",
                }
            ]
        }
    )

    connectors = list_configured_connectors(settings=settings)
    definition = get_connector_config("db-drive", settings=settings)

    assert [(item.connector_id, item.kb_id) for item in connectors] == [("db-drive", "db-kb")]
    assert definition.config.folder_id == "db-folder"


def test_connector_operations_require_explicit_settings(monkeypatch, tmp_path):
    from fleetent.knowledge_base import get_connector_config, list_configured_connectors

    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    (tmp_path / "platform.yaml").write_text(
        """
knowledge:
  knowledge_bases:
    - id: engineering
      tenant_id: default
      sources:
        - id: yaml-drive
          type: google_drive
          folder_id: folder-1
          credential_ref: file:///secure/google.json
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="explicit connector settings are required"):
        list_configured_connectors()

    with pytest.raises(ValueError, match="explicit connector settings are required"):
        get_connector_config("yaml-drive")
