from __future__ import annotations

from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.schema_migrations import migrate


async def test_new_google_drive_file_is_planned_for_ingest(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    del database
    from fleetent.knowledge_base import SyncAction
    from fleetent.knowledge_base.connectors.google_drive import (
        FakeGoogleDriveClient,
        plan_google_drive_sync,
    )

    plan = await plan_google_drive_sync(
        _config(),
        client=FakeGoogleDriveClient(files_by_folder={"folder-1": [_file("doc-1", rev="rev-1")]}),
    )

    assert [item.action for item in plan.items] == [SyncAction.INGEST_NEW]
    assert plan.items[0].source_path == "drive://doc-1"
    assert plan.items[0].tenant_id == "tenant-a"
    assert plan.items[0].kb_id == "support"
    assert plan.summary.ingested == 1


async def test_changed_google_drive_file_is_planned_for_reingest(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import SyncAction, runtime
    from fleetent.knowledge_base.connectors import (
        LocalSourceState,
        LocalSourceStateStore,
    )
    from fleetent.knowledge_base.connectors.google_drive import (
        FakeGoogleDriveClient,
        google_drive_fingerprint,
        plan_google_drive_sync,
    )

    old_file = _file("doc-1", rev="rev-1")
    LocalSourceStateStore(database).upsert(
        LocalSourceState(
            source_id="gdrive-team",
            tenant_id="tenant-a",
            kb_id="support",
            source_path="drive://doc-1",
            mtime_ns=1,
            content_hash=google_drive_fingerprint(old_file),
            document_id="kb-doc-1",
        )
    )
    assert runtime._database() == database

    plan = await plan_google_drive_sync(
        _config(),
        client=FakeGoogleDriveClient(files_by_folder={"folder-1": [_file("doc-1", rev="rev-2")]}),
    )

    assert [item.action for item in plan.items] == [SyncAction.REINGEST_CHANGED]
    assert plan.items[0].document_id == "kb-doc-1"
    assert plan.summary.changed == 1


async def test_unchanged_google_drive_file_is_planned_for_skip(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import SyncAction
    from fleetent.knowledge_base.connectors import (
        LocalSourceState,
        LocalSourceStateStore,
    )
    from fleetent.knowledge_base.connectors.google_drive import (
        FakeGoogleDriveClient,
        google_drive_fingerprint,
        plan_google_drive_sync,
    )

    file = _file("doc-1", rev="rev-1")
    LocalSourceStateStore(database).upsert(
        LocalSourceState(
            source_id="gdrive-team",
            tenant_id="tenant-a",
            kb_id="support",
            source_path="drive://doc-1",
            mtime_ns=plan_modified_time_ns(file),
            content_hash=google_drive_fingerprint(file),
            document_id="kb-doc-1",
        )
    )

    plan = await plan_google_drive_sync(
        _config(),
        client=FakeGoogleDriveClient(files_by_folder={"folder-1": [file]}),
    )

    assert [item.action for item in plan.items] == [SyncAction.SKIP_UNCHANGED]
    assert plan.summary.unchanged == 1


async def test_missing_google_drive_source_state_is_planned_for_archive(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import SyncAction
    from fleetent.knowledge_base.connectors import (
        LocalSourceState,
        LocalSourceStateStore,
    )
    from fleetent.knowledge_base.connectors.google_drive import (
        FakeGoogleDriveClient,
        plan_google_drive_sync,
    )

    LocalSourceStateStore(database).upsert(
        LocalSourceState(
            source_id="gdrive-team",
            tenant_id="tenant-a",
            kb_id="support",
            source_path="drive://missing",
            mtime_ns=1,
            content_hash="old",
            document_id="kb-doc-1",
        )
    )

    plan = await plan_google_drive_sync(
        _config(),
        client=FakeGoogleDriveClient(files_by_folder={"folder-1": []}),
    )

    assert [item.action for item in plan.items] == [SyncAction.ARCHIVE_MISSING]
    assert plan.items[0].document_id == "kb-doc-1"
    assert plan.summary.archived == 1


def _config():
    from fleetent.knowledge_base import GoogleDriveConnectorConfig

    return GoogleDriveConnectorConfig(
        connector_id="gdrive-team",
        tenant_id="tenant-a",
        kb_id="support",
        folder_id="folder-1",
        credential_ref="token.json",
    )


def _file(file_id: str, *, rev: str):
    from fleetent.knowledge_base.connectors.google_drive import GoogleDriveFile

    return GoogleDriveFile(
        id=file_id,
        name="Runbook",
        mime_type="application/vnd.google-apps.document",
        modified_time="2026-06-02T00:00:00+00:00",
        revision_id=rev,
    )


def plan_modified_time_ns(file) -> int:
    from fleetent.knowledge_base.connectors.google_drive import _modified_time_ns

    return _modified_time_ns(file)


def _patch_knowledge_runtime(monkeypatch, tmp_path):
    from fleetent.knowledge_base import runtime

    db_path = tmp_path / "knowledge.db"
    migrate(SQLiteDatabase(path=db_path), KB_MIGRATIONS)
    database = create_database(f"sqlite:///{db_path}")
    settings = Settings(
        anthropic_api_key="test-key",
        knowledge_base=KnowledgeBaseSettings(chunk_size=100, chunk_overlap=0),
    )
    monkeypatch.setattr(runtime, "_database", lambda: database)
    monkeypatch.setattr(runtime, "_kb_vector_backend", None)
    monkeypatch.setattr(runtime, "_settings", lambda: settings)
    return database
