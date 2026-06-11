import hashlib

from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.schema_migrations import migrate


def test_sync_planner_public_api_is_importable():
    from fleetent.knowledge_base import (
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

    from fleetent.knowledge_base import plan_local_directory_sync
    from fleetent.knowledge_base.connectors import LocalDirectorySourceConfig

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

    from fleetent.knowledge_base import SyncAction, plan_local_directory_sync
    from fleetent.knowledge_base.connectors import LocalDirectorySourceConfig

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

    from fleetent.knowledge_base import SyncAction, plan_local_directory_sync, runtime
    from fleetent.knowledge_base.connectors import (
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

    from fleetent.knowledge_base import SyncAction, plan_local_directory_sync, runtime
    from fleetent.knowledge_base.connectors import (
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

    from fleetent.knowledge_base import plan_local_directory_sync
    from fleetent.knowledge_base.connectors import LocalDirectorySourceConfig

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

    from fleetent.knowledge_base import SyncAction, plan_local_directory_sync
    from fleetent.knowledge_base.connectors import LocalDirectorySourceConfig

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

    from fleetent.knowledge_base import SyncAction, plan_local_directory_sync, runtime
    from fleetent.knowledge_base.connectors import (
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


async def test_execute_sync_plan_skips_unchanged_items(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()

    from fleetent.knowledge_base import SyncAction, execute_sync_plan
    from fleetent.knowledge_base.connectors import LocalDirectorySourceConfig

    plan = _build_plan(
        root,
        [_plan_item(SyncAction.SKIP_UNCHANGED, root, "a.md")],
        unsupported=2,
    )
    config = LocalDirectorySourceConfig(
        source_id="local-docs", root_path=root, allowed_roots=[root]
    )
    plan = _with_config(plan, config)

    summary = await execute_sync_plan(plan)

    assert summary.unchanged == 1
    assert summary.skipped == 3  # unsupported (2) + the one skipped item
    assert summary.ingested == 0
    assert summary.failed == 0


async def test_execute_sync_plan_ingests_new_file_and_records_state(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    document_path = root / "runbook.md"
    document_path.write_text("# Runbook\nStart service", encoding="utf-8")

    ingested = _fake_ingest(monkeypatch, document_id="doc-new")

    from fleetent.knowledge_base import SyncAction, execute_sync_plan
    from fleetent.knowledge_base.connectors import (
        LocalDirectorySourceConfig,
        LocalSourceStateStore,
    )

    item = _plan_item(
        SyncAction.INGEST_NEW,
        root,
        "runbook.md",
        document_format="markdown",
        mtime_ns=document_path.stat().st_mtime_ns,
        content_hash="abc123",
    )
    config = LocalDirectorySourceConfig(
        source_id="local-docs", root_path=root, allowed_roots=[root]
    )
    plan = _with_config(_build_plan(root, [item]), config)

    summary = await execute_sync_plan(plan)

    assert summary.ingested == 1
    assert summary.failed == 0
    assert len(ingested) == 1
    states = LocalSourceStateStore(database).list_for_source(
        source_id="local-docs", tenant_id="tenant-a", kb_id="support"
    )
    assert [state.document_id for state in states] == ["doc-new"]


async def test_execute_sync_plan_reingest_deletes_then_ingests(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    document_path = root / "runbook.md"
    document_path.write_text("# Runbook\nUpdated", encoding="utf-8")

    deleted = _fake_delete(monkeypatch)
    _fake_ingest(monkeypatch, document_id="doc-reingest")

    from fleetent.knowledge_base import SyncAction, execute_sync_plan
    from fleetent.knowledge_base.connectors import LocalDirectorySourceConfig

    item = _plan_item(
        SyncAction.REINGEST_CHANGED,
        root,
        "runbook.md",
        document_format="markdown",
        mtime_ns=document_path.stat().st_mtime_ns,
        content_hash="def456",
        document_id="doc-old",
    )
    config = LocalDirectorySourceConfig(
        source_id="local-docs", root_path=root, allowed_roots=[root]
    )
    plan = _with_config(_build_plan(root, [item]), config)

    summary = await execute_sync_plan(plan)

    assert summary.ingested == 1
    assert deleted == ["doc-old"]


async def test_execute_sync_plan_deletes_missing_document(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    missing_path = str((root / "gone.md").resolve())

    deleted = _fake_delete(monkeypatch)

    from fleetent.knowledge_base import SyncAction, execute_sync_plan
    from fleetent.knowledge_base.connectors import (
        LocalDirectorySourceConfig,
        LocalSourceState,
        LocalSourceStateStore,
    )

    LocalSourceStateStore(database).upsert(
        LocalSourceState(
            source_id="local-docs",
            tenant_id="tenant-a",
            kb_id="support",
            source_path=missing_path,
            mtime_ns=1,
            content_hash="old",
            document_id="doc-gone",
        )
    )
    item = _plan_item(
        SyncAction.DELETE_MISSING,
        root,
        "gone.md",
        source_path=missing_path,
        document_id="doc-gone",
    )
    config = LocalDirectorySourceConfig(
        source_id="local-docs", root_path=root, allowed_roots=[root]
    )
    plan = _with_config(_build_plan(root, [item]), config)

    summary = await execute_sync_plan(plan)

    assert summary.deleted == 1
    assert deleted == ["doc-gone"]
    remaining = LocalSourceStateStore(database).list_for_source(
        source_id="local-docs", tenant_id="tenant-a", kb_id="support"
    )
    assert remaining == []


async def test_execute_sync_plan_delete_without_document_id_counts_failed(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    _fake_delete(monkeypatch)

    from fleetent.knowledge_base import SyncAction, execute_sync_plan
    from fleetent.knowledge_base.connectors import LocalDirectorySourceConfig

    item = _plan_item(SyncAction.DELETE_MISSING, root, "gone.md", document_id=None)
    config = LocalDirectorySourceConfig(
        source_id="local-docs", root_path=root, allowed_roots=[root]
    )
    plan = _with_config(_build_plan(root, [item]), config)

    summary = await execute_sync_plan(plan)

    assert summary.failed == 1
    assert summary.deleted == 0


async def test_execute_sync_plan_unsupported_action_counts_failed(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()

    from fleetent.knowledge_base import SyncAction, execute_sync_plan
    from fleetent.knowledge_base.connectors import LocalDirectorySourceConfig

    item = _plan_item(SyncAction.AUTH_FAILED, root, "a.md")
    config = LocalDirectorySourceConfig(
        source_id="local-docs", root_path=root, allowed_roots=[root]
    )
    plan = _with_config(_build_plan(root, [item]), config)

    summary = await execute_sync_plan(plan)

    assert summary.failed == 1
    assert summary.ingested == 0


async def test_execute_sync_plan_unsupported_format_counts_failed(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    (root / "data.bin").write_bytes(b"binary")
    _fake_ingest(monkeypatch, document_id="doc-x")

    from fleetent.knowledge_base import SyncAction, execute_sync_plan
    from fleetent.knowledge_base.connectors import LocalDirectorySourceConfig

    item = _plan_item(
        SyncAction.INGEST_NEW,
        root,
        "data.bin",
        document_format="binary",
        mtime_ns=1,
        content_hash="hash",
    )
    config = LocalDirectorySourceConfig(
        source_id="local-docs", root_path=root, allowed_roots=[root]
    )
    plan = _with_config(_build_plan(root, [item]), config)

    summary = await execute_sync_plan(plan)

    assert summary.failed == 1


async def test_plan_local_directory_sync_rejects_ref_without_path(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()

    from fleetent.knowledge_base import plan_local_directory_sync, sync_planner
    from fleetent.knowledge_base.connectors import LocalDirectorySourceConfig
    from fleetent.knowledge_base.connectors.base import DocumentRef

    class _PathlessSource:
        def __init__(self, *args, **kwargs):
            pass

        def list_documents(self):
            return [DocumentRef(id="x", filename="x.md", format="markdown", path=None)]

        def count_unsupported_documents(self):
            return 0

        def fetch(self, ref):
            return b"data"

    monkeypatch.setattr(sync_planner, "LocalDirectoryDataSource", _PathlessSource)

    config = LocalDirectorySourceConfig(
        source_id="local-docs", root_path=root, allowed_roots=[root]
    )

    try:
        await plan_local_directory_sync(config, tenant_id="tenant-a", kb_id="support")
    except ValueError as exc:
        assert "must include path" in str(exc)
    else:
        raise AssertionError("pathless ref was accepted")


def _build_plan(root, items, unsupported=0):
    from fleetent.knowledge_base import SyncPlan, SyncPlanSummary
    from fleetent.knowledge_base.connectors import LocalDirectorySourceConfig

    config = LocalDirectorySourceConfig(
        source_id="local-docs", root_path=root, allowed_roots=[root]
    )
    return SyncPlan(
        source_config=config,
        tenant_id="tenant-a",
        kb_id="support",
        items=items,
        summary=SyncPlanSummary(
            scanned=len(items) + unsupported,
            planned=len(items),
            unsupported=unsupported,
        ),
    )


def _with_config(plan, config):
    from dataclasses import replace

    return replace(plan, source_config=config)


def _plan_item(
    action,
    root,
    filename,
    *,
    document_format="markdown",
    source_path=None,
    mtime_ns=None,
    content_hash=None,
    document_id=None,
):
    from fleetent.knowledge_base import SyncPlanItem

    return SyncPlanItem(
        action=action,
        source_id="local-docs",
        tenant_id="tenant-a",
        kb_id="support",
        source_path=source_path if source_path is not None else str((root / filename).resolve()),
        filename=filename,
        document_format=document_format,
        mtime_ns=mtime_ns,
        content_hash=content_hash,
        document_id=document_id,
    )


def _fake_ingest(monkeypatch, *, document_id):
    from fleetent.knowledge_base import runtime
    from fleetent.knowledge_base.models import KnowledgeDocument

    calls = []

    async def _ingest_parsed(parsed, *, tenant_id, kb_id, source, source_url):
        calls.append(parsed)
        return KnowledgeDocument(
            id=document_id,
            tenant_id=tenant_id,
            kb_id=kb_id,
            filename=parsed.filename,
            source=source,
            source_url=source_url,
        )

    monkeypatch.setattr(runtime, "ingest_parsed", _ingest_parsed)
    return calls


def _fake_delete(monkeypatch):
    from fleetent.knowledge_base import runtime

    deleted = []

    async def _delete(document_id):
        deleted.append(document_id)

    monkeypatch.setattr(runtime, "delete", _delete)
    return deleted


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
