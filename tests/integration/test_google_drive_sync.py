from __future__ import annotations

from unittest.mock import AsyncMock

from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import create_database
from tests.integration.test_migrations import apply_migrations


async def test_google_drive_sync_ingests_new_files_into_tenant_kb(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import sync_google_drive
    from fleetent.knowledge_base.connectors.google_drive import (
        FakeGoogleDriveClient,
    )

    summary = await sync_google_drive(
        _config(),
        client=FakeGoogleDriveClient(
            files_by_folder={"folder-1": [_google_doc("doc-1", "Runbook")]},
            exports={"doc-1": "<h1>Runbook</h1><p>Restart service</p>"},
        ),
    )

    documents = database.execute(
        """
        SELECT tenant_id, kb_id, filename, source, source_url
        FROM knowledge_documents
        """
    ).fetchall()
    chunks = database.execute("SELECT content FROM knowledge_chunks").fetchall()

    assert summary.scanned == 1
    assert summary.ingested == 1
    assert summary.failed == 0
    assert documents == [
        {
            "tenant_id": "tenant-a",
            "kb_id": "support",
            "filename": "Runbook.html",
            "source": "google_drive:gdrive-team",
            "source_url": "drive://doc-1",
        }
    ]
    assert chunks[0]["content"] == "Restart service"


async def test_google_drive_reingest_changed_replaces_old_document(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import sync_google_drive
    from fleetent.knowledge_base.connectors.google_drive import FakeGoogleDriveClient

    first = await sync_google_drive(
        _config(),
        client=FakeGoogleDriveClient(
            files_by_folder={"folder-1": [_google_doc("doc-1", "Runbook", rev="rev-1")]},
            exports={"doc-1": "<h1>Runbook</h1><p>First version</p>"},
        ),
    )
    second = await sync_google_drive(
        _config(),
        client=FakeGoogleDriveClient(
            files_by_folder={"folder-1": [_google_doc("doc-1", "Runbook", rev="rev-2")]},
            exports={"doc-1": "<h1>Runbook</h1><p>Second version</p>"},
        ),
    )

    documents = database.execute("SELECT id, filename FROM knowledge_documents").fetchall()
    chunks = database.execute("SELECT content FROM knowledge_chunks").fetchall()

    assert first.ingested == 1
    assert second.changed == 1
    assert second.ingested == 1
    assert len(documents) == 1
    assert chunks == [{"content": "Second version"}]


async def test_google_drive_archive_missing_does_not_call_physical_delete(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import runtime, sync_google_drive
    from fleetent.knowledge_base.connectors.google_drive import FakeGoogleDriveClient

    await sync_google_drive(
        _config(),
        client=FakeGoogleDriveClient(
            files_by_folder={"folder-1": [_google_doc("doc-1", "Runbook")]},
            exports={"doc-1": "<h1>Runbook</h1><p>Archived later</p>"},
        ),
    )
    delete = AsyncMock()
    monkeypatch.setattr(runtime, "delete", delete)

    summary = await sync_google_drive(
        _config(),
        client=FakeGoogleDriveClient(files_by_folder={"folder-1": []}),
    )

    documents = database.execute("SELECT filename, archived_at FROM knowledge_documents").fetchall()
    chunks = database.execute("SELECT content FROM knowledge_chunks").fetchall()

    assert summary.archived == 1
    delete.assert_not_awaited()
    assert documents[0]["filename"] == "Runbook.html"
    assert documents[0]["archived_at"] is not None
    assert chunks == []


async def test_google_drive_item_failure_does_not_block_following_items(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import sync_google_drive
    from fleetent.knowledge_base.connectors.google_drive import FakeGoogleDriveClient

    summary = await sync_google_drive(
        _config(),
        client=FakeGoogleDriveClient(
            files_by_folder={
                "folder-1": [
                    _google_doc("missing-export", "Broken"),
                    _google_doc("doc-2", "Good"),
                ]
            },
            exports={"doc-2": "<h1>Good</h1><p>Still ingested</p>"},
        ),
    )

    assert summary.failed == 1
    assert summary.ingested == 1


async def test_sync_google_drive_uses_plan_then_executor(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import sync_google_drive
    from fleetent.knowledge_base.connectors.google_drive import (
        FakeGoogleDriveClient,
        GoogleDriveSyncPlan,
    )

    calls: list[str] = []

    async def fake_plan(config, *, client):
        calls.append("plan")
        return GoogleDriveSyncPlan(config=config, items=[], files={}, summary=_empty_summary())

    async def fake_execute(plan, *, client):
        calls.append("execute")
        return _execution_summary()

    monkeypatch.setattr(
        "fleetent.knowledge_base.connectors.google_drive.plan_google_drive_sync",
        fake_plan,
    )
    monkeypatch.setattr(
        "fleetent.knowledge_base.connectors.google_drive.execute_google_drive_sync_plan",
        fake_execute,
    )

    summary = await sync_google_drive(_config(), client=FakeGoogleDriveClient())

    assert calls == ["plan", "execute"]
    assert summary.scanned == 0


def _config():
    from fleetent.knowledge_base import GoogleDriveConnectorConfig

    return GoogleDriveConnectorConfig(
        connector_id="gdrive-team",
        tenant_id="tenant-a",
        kb_id="support",
        folder_id="folder-1",
        credential_ref="token.json",
    )


def _google_doc(file_id: str, name: str, *, rev: str = "rev-1"):
    from fleetent.knowledge_base.connectors.google_drive import GoogleDriveFile

    return GoogleDriveFile(
        id=file_id,
        name=name,
        mime_type="application/vnd.google-apps.document",
        modified_time="2026-06-02T00:00:00+00:00",
        revision_id=rev,
    )


def _empty_summary():
    from fleetent.knowledge_base import SyncPlanSummary

    return SyncPlanSummary(scanned=0, planned=0)


def _execution_summary():
    from fleetent.knowledge_base.connectors.google_drive import GoogleDriveSyncSummary

    return GoogleDriveSyncSummary(scanned=0, planned=0)


def _patch_knowledge_runtime(monkeypatch, tmp_path):
    from fleetent.knowledge_base import runtime

    db_path = tmp_path / "knowledge.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    settings = Settings(
        anthropic_api_key="test-key",
        knowledge_base=KnowledgeBaseSettings(chunk_size=100, chunk_overlap=0),
    )
    monkeypatch.setattr(runtime, "_database", lambda: database)
    monkeypatch.setattr(runtime, "_settings", lambda: settings)
    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    monkeypatch.setattr(runtime.vector_store, "delete", _noop_delete)
    return database


async def _noop_upsert(chunk_id: str, content: str, namespace: str) -> None:
    return None


async def _noop_delete(chunk_id: str, namespace: str) -> None:
    return None
