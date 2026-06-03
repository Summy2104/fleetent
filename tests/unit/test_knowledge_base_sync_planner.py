import hashlib

from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import create_database
from tests.integration.test_migrations import apply_migrations


def test_sync_planner_public_api_is_importable():
    from fleetent.intelligence.knowledge_base import (
        SyncAction,
        SyncExecutionSummary,
        SyncPlan,
        SyncPlanItem,
        SyncPlanSummary,
        execute_sync_plan,
        plan_local_directory_sync,
    )

    assert SyncAction.INGEST_NEW.value == "ingest_new"
    assert SyncAction.REINGEST_CHANGED.value == "reingest_changed"
    assert SyncAction.SKIP_UNCHANGED.value == "skip_unchanged"
    assert SyncAction.DELETE_MISSING.value == "delete_missing"
    assert SyncPlan is not None
    assert SyncPlanItem is not None
    assert SyncPlanSummary is not None
    assert SyncExecutionSummary is not None
    assert plan_local_directory_sync is not None
    assert execute_sync_plan is not None


async def test_empty_local_directory_plan_has_no_items(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()

    from fleetent.intelligence.knowledge_base import plan_local_directory_sync
    from fleetent.intelligence.knowledge_base.connectors import LocalDirectorySourceConfig

    plan = await plan_local_directory_sync(
        LocalDirectorySourceConfig(
            source_id="local-docs",
            root_path=root,
            allowed_roots=[root],
        ),
        tenant_id="tenant-a",
        kb_id="support",
    )

    assert plan.items == []
    assert plan.summary.scanned == 0
    assert plan.summary.planned == 0
    assert plan.summary.unsupported == 0


async def test_new_file_is_planned_for_ingest(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    document_path = root / "runbook.md"
    document_path.write_text("# Runbook\nStart service", encoding="utf-8")

    from fleetent.intelligence.knowledge_base import SyncAction, plan_local_directory_sync
    from fleetent.intelligence.knowledge_base.connectors import LocalDirectorySourceConfig

    plan = await plan_local_directory_sync(
        LocalDirectorySourceConfig(
            source_id="local-docs",
            root_path=root,
            allowed_roots=[root],
        ),
        tenant_id="tenant-a",
        kb_id="support",
    )

    assert [item.action for item in plan.items] == [SyncAction.INGEST_NEW]
    assert plan.items[0].source_path == str(document_path.resolve())
    assert plan.items[0].content_hash == hashlib.sha256(b"# Runbook\nStart service").hexdigest()
    assert plan.summary.scanned == 1
    assert plan.summary.planned == 1


async def test_changed_file_is_planned_for_reingest(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    document_path = root / "runbook.md"
    document_path.write_text("# Runbook\nSecond version", encoding="utf-8")

    from fleetent.intelligence.knowledge_base import SyncAction, plan_local_directory_sync, runtime
    from fleetent.intelligence.knowledge_base.connectors import (
        LocalDirectorySourceConfig,
        LocalSourceState,
        LocalSourceStateStore,
    )

    LocalSourceStateStore(runtime._database()).upsert(
        LocalSourceState(
            source_id="local-docs",
            tenant_id="tenant-a",
            kb_id="support",
            source_path=str(document_path.resolve()),
            mtime_ns=1,
            content_hash="old-hash",
            document_id="doc-old",
        )
    )

    plan = await plan_local_directory_sync(
        LocalDirectorySourceConfig(
            source_id="local-docs",
            root_path=root,
            allowed_roots=[root],
        ),
        tenant_id="tenant-a",
        kb_id="support",
    )

    assert [item.action for item in plan.items] == [SyncAction.REINGEST_CHANGED]
    assert plan.items[0].document_id == "doc-old"


async def test_unchanged_file_is_planned_for_skip(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    document_path = root / "runbook.md"
    content = b"# Runbook\nStable"
    document_path.write_bytes(content)
    stat = document_path.stat()

    from fleetent.intelligence.knowledge_base import SyncAction, plan_local_directory_sync, runtime
    from fleetent.intelligence.knowledge_base.connectors import (
        LocalDirectorySourceConfig,
        LocalSourceState,
        LocalSourceStateStore,
    )

    LocalSourceStateStore(runtime._database()).upsert(
        LocalSourceState(
            source_id="local-docs",
            tenant_id="tenant-a",
            kb_id="support",
            source_path=str(document_path.resolve()),
            mtime_ns=stat.st_mtime_ns,
            content_hash=hashlib.sha256(content).hexdigest(),
            document_id="doc-existing",
        )
    )

    plan = await plan_local_directory_sync(
        LocalDirectorySourceConfig(
            source_id="local-docs",
            root_path=root,
            allowed_roots=[root],
        ),
        tenant_id="tenant-a",
        kb_id="support",
    )

    assert [item.action for item in plan.items] == [SyncAction.SKIP_UNCHANGED]
    assert plan.summary.unchanged == 1


async def test_unsupported_files_are_counted_but_not_planned_for_ingest(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    (root / "archive.bin").write_bytes(b"binary")

    from fleetent.intelligence.knowledge_base import plan_local_directory_sync
    from fleetent.intelligence.knowledge_base.connectors import LocalDirectorySourceConfig

    plan = await plan_local_directory_sync(
        LocalDirectorySourceConfig(
            source_id="local-docs",
            root_path=root,
            allowed_roots=[root],
        ),
        tenant_id="tenant-a",
        kb_id="support",
    )

    assert plan.items == []
    assert plan.summary.scanned == 1
    assert plan.summary.unsupported == 1
    assert plan.summary.planned == 0


async def test_advanced_files_are_planned_for_ingest(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    for filename in ["report.pdf", "guide.docx", "deck.pptx", "book.xlsx"]:
        (root / filename).write_bytes(b"advanced")

    from fleetent.intelligence.knowledge_base import SyncAction, plan_local_directory_sync
    from fleetent.intelligence.knowledge_base.connectors import LocalDirectorySourceConfig

    plan = await plan_local_directory_sync(
        LocalDirectorySourceConfig(
            source_id="local-docs",
            root_path=root,
            allowed_roots=[root],
        ),
        tenant_id="tenant-a",
        kb_id="support",
    )

    assert [(item.filename, item.document_format, item.action) for item in plan.items] == [
        ("book.xlsx", "xlsx", SyncAction.INGEST_NEW),
        ("deck.pptx", "pptx", SyncAction.INGEST_NEW),
        ("guide.docx", "docx", SyncAction.INGEST_NEW),
        ("report.pdf", "pdf", SyncAction.INGEST_NEW),
    ]
    assert plan.summary.scanned == 4
    assert plan.summary.unsupported == 0


async def test_missing_source_state_is_planned_for_delete(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    missing_path = str((root / "deleted.md").resolve())

    from fleetent.intelligence.knowledge_base import SyncAction, plan_local_directory_sync, runtime
    from fleetent.intelligence.knowledge_base.connectors import (
        LocalDirectorySourceConfig,
        LocalSourceState,
        LocalSourceStateStore,
    )

    LocalSourceStateStore(runtime._database()).upsert(
        LocalSourceState(
            source_id="local-docs",
            tenant_id="tenant-a",
            kb_id="support",
            source_path=missing_path,
            mtime_ns=1,
            content_hash="old-hash",
            document_id="doc-deleted",
        )
    )

    plan = await plan_local_directory_sync(
        LocalDirectorySourceConfig(
            source_id="local-docs",
            root_path=root,
            allowed_roots=[root],
        ),
        tenant_id="tenant-a",
        kb_id="support",
    )

    assert [item.action for item in plan.items] == [SyncAction.DELETE_MISSING]
    assert plan.items[0].source_id == "local-docs"
    assert plan.items[0].tenant_id == "tenant-a"
    assert plan.items[0].kb_id == "support"
    assert plan.items[0].source_path == missing_path
    assert plan.items[0].document_id == "doc-deleted"
    assert plan.summary.deleted == 1


def _patch_knowledge_runtime(monkeypatch, tmp_path):
    from fleetent.intelligence.knowledge_base import runtime

    db_path = tmp_path / "knowledge.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    settings = Settings(
        anthropic_api_key="test-key",
        knowledge_base=KnowledgeBaseSettings(chunk_size=100, chunk_overlap=0),
    )
    monkeypatch.setattr(runtime, "_database", lambda: database)
    monkeypatch.setattr(runtime, "_settings", lambda: settings)
    return database
