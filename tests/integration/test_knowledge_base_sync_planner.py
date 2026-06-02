import hashlib

from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import create_database
from tests.integration.test_migrations import apply_migrations


async def test_execute_ingest_new_parses_ingests_and_updates_source_state(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    document_path = root / "runbook.md"
    content = b"# Runbook\nRestart the worker"
    document_path.write_bytes(content)

    from fleetent.intelligence.knowledge_base import (
        SyncAction,
        execute_sync_plan,
        plan_local_directory_sync,
    )
    from fleetent.intelligence.knowledge_base.connectors import LocalDirectorySourceConfig

    config = LocalDirectorySourceConfig(
        source_id="local-docs",
        root_path=root,
        allowed_roots=[root],
    )
    plan = await plan_local_directory_sync(config, tenant_id="tenant-a", kb_id="support")

    summary = await execute_sync_plan(plan)

    documents = database.execute("SELECT filename, source_url FROM knowledge_documents").fetchall()
    states = database.execute(
        "SELECT source_path, content_hash, document_id FROM knowledge_source_states"
    )
    state_rows = states.fetchall()
    assert [item.action for item in plan.items] == [SyncAction.INGEST_NEW]
    assert summary.ingested == 1
    assert summary.failed == 0
    assert [(row["filename"], row["source_url"]) for row in documents] == [
        ("runbook.md", str(document_path.resolve()))
    ]
    assert state_rows == [
        {
            "source_path": str(document_path.resolve()),
            "content_hash": hashlib.sha256(content).hexdigest(),
            "document_id": state_rows[0]["document_id"],
        }
    ]


async def test_execute_reingest_changed_deletes_old_document_and_updates_state(
    monkeypatch,
    tmp_path,
):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    document_path = root / "runbook.md"
    document_path.write_text("# Runbook\nFirst version", encoding="utf-8")

    from fleetent.intelligence.knowledge_base import (
        SyncAction,
        execute_sync_plan,
        plan_local_directory_sync,
    )
    from fleetent.intelligence.knowledge_base.connectors import LocalDirectorySourceConfig

    config = LocalDirectorySourceConfig(
        source_id="local-docs",
        root_path=root,
        allowed_roots=[root],
    )
    first_plan = await plan_local_directory_sync(config, tenant_id="tenant-a", kb_id="support")
    first_summary = await execute_sync_plan(first_plan)
    first_document_id = database.execute("SELECT id FROM knowledge_documents").fetchone()["id"]

    document_path.write_text("# Runbook\nSecond version", encoding="utf-8")
    second_plan = await plan_local_directory_sync(config, tenant_id="tenant-a", kb_id="support")
    second_summary = await execute_sync_plan(second_plan)

    documents = database.execute("SELECT id, filename FROM knowledge_documents").fetchall()
    state = database.execute("SELECT document_id FROM knowledge_source_states").fetchone()
    assert first_summary.ingested == 1
    assert [item.action for item in second_plan.items] == [SyncAction.REINGEST_CHANGED]
    assert second_summary.ingested == 1
    assert second_summary.failed == 0
    assert len(documents) == 1
    assert documents[0]["filename"] == "runbook.md"
    assert documents[0]["id"] != first_document_id
    assert state["document_id"] == documents[0]["id"]


async def test_execute_delete_missing_deletes_document_and_source_state(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    document_path = root / "runbook.md"
    document_path.write_text("# Runbook\nTemporary", encoding="utf-8")

    from fleetent.intelligence.knowledge_base import (
        SyncAction,
        execute_sync_plan,
        plan_local_directory_sync,
    )
    from fleetent.intelligence.knowledge_base.connectors import LocalDirectorySourceConfig

    config = LocalDirectorySourceConfig(
        source_id="local-docs",
        root_path=root,
        allowed_roots=[root],
    )
    await execute_sync_plan(await plan_local_directory_sync(config, "tenant-a", "support"))
    document_path.unlink()
    delete_plan = await plan_local_directory_sync(config, "tenant-a", "support")

    summary = await execute_sync_plan(delete_plan)

    documents = database.execute("SELECT id FROM knowledge_documents").fetchall()
    states = database.execute("SELECT source_path FROM knowledge_source_states").fetchall()
    assert [item.action for item in delete_plan.items] == [SyncAction.DELETE_MISSING]
    assert summary.deleted == 1
    assert summary.failed == 0
    assert documents == []
    assert states == []


async def test_execute_skip_unchanged_does_not_parse_ingest_or_delete(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    document_path = root / "runbook.md"
    document_path.write_text("# Runbook\nStable", encoding="utf-8")

    from fleetent.intelligence.knowledge_base import (
        SyncAction,
        execute_sync_plan,
        plan_local_directory_sync,
        runtime,
    )
    from fleetent.intelligence.knowledge_base.connectors import LocalDirectorySourceConfig

    config = LocalDirectorySourceConfig(
        source_id="local-docs",
        root_path=root,
        allowed_roots=[root],
    )
    await execute_sync_plan(await plan_local_directory_sync(config, "tenant-a", "support"))
    unchanged_plan = await plan_local_directory_sync(config, "tenant-a", "support")
    monkeypatch.setattr(runtime, "ingest_parsed", _raise_if_called)
    monkeypatch.setattr(runtime, "delete", _raise_if_called)

    summary = await execute_sync_plan(unchanged_plan)

    assert [item.action for item in unchanged_plan.items] == [SyncAction.SKIP_UNCHANGED]
    assert summary.skipped == 1
    assert summary.unchanged == 1
    assert summary.failed == 0
    assert len(database.execute("SELECT id FROM knowledge_documents").fetchall()) == 1


async def test_execute_item_failure_does_not_block_later_items(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    bad_path = root / "bad.md"
    good_path = root / "good.md"
    bad_path.write_text("# Bad\nInvalid format", encoding="utf-8")
    good_path.write_text("# Good\nValid format", encoding="utf-8")

    from fleetent.intelligence.knowledge_base import (
        SyncAction,
        SyncPlan,
        SyncPlanItem,
        SyncPlanSummary,
        execute_sync_plan,
    )
    from fleetent.intelligence.knowledge_base.connectors import LocalDirectorySourceConfig

    config = LocalDirectorySourceConfig(
        source_id="local-docs",
        root_path=root,
        allowed_roots=[root],
    )
    plan = SyncPlan(
        source_config=config,
        tenant_id="tenant-a",
        kb_id="support",
        items=[
            SyncPlanItem(
                action=SyncAction.INGEST_NEW,
                source_id="local-docs",
                tenant_id="tenant-a",
                kb_id="support",
                source_path=str(bad_path.resolve()),
                filename="bad.md",
                document_format="unsupported",
                mtime_ns=bad_path.stat().st_mtime_ns,
                content_hash="bad-hash",
            ),
            SyncPlanItem(
                action=SyncAction.INGEST_NEW,
                source_id="local-docs",
                tenant_id="tenant-a",
                kb_id="support",
                source_path=str(good_path.resolve()),
                filename="good.md",
                document_format="markdown",
                mtime_ns=good_path.stat().st_mtime_ns,
                content_hash=hashlib.sha256(good_path.read_bytes()).hexdigest(),
            ),
        ],
        summary=SyncPlanSummary(scanned=2, planned=2, ingested=2),
    )

    summary = await execute_sync_plan(plan)

    documents = database.execute("SELECT filename FROM knowledge_documents").fetchall()
    states = database.execute("SELECT source_path FROM knowledge_source_states").fetchall()
    assert summary.failed == 1
    assert summary.ingested == 1
    assert [row["filename"] for row in documents] == ["good.md"]
    assert [row["source_path"] for row in states] == [str(good_path.resolve())]


async def test_sync_local_directory_summary_matches_plan_execution(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    (root / "runbook.md").write_text("# Runbook\nSync", encoding="utf-8")
    (root / "archive.pdf").write_bytes(b"%PDF")

    from fleetent.intelligence.knowledge_base.connectors import (
        LocalDirectorySourceConfig,
        sync_local_directory,
    )

    summary = await sync_local_directory(
        LocalDirectorySourceConfig(
            source_id="local-docs",
            root_path=root,
            allowed_roots=[root],
        ),
        tenant_id="tenant-a",
        kb_id="support",
    )

    assert summary.scanned == 2
    assert summary.ingested == 1
    assert summary.skipped == 1
    assert summary.failed == 0
    assert summary.unsupported == 1
    assert summary.unchanged == 0
    assert summary.deleted == 0


async def test_repeated_sync_is_idempotent_and_reports_unchanged(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    (root / "runbook.md").write_text("# Runbook\nStable", encoding="utf-8")

    from fleetent.intelligence.knowledge_base.connectors import (
        LocalDirectorySourceConfig,
        sync_local_directory,
    )

    config = LocalDirectorySourceConfig(
        source_id="local-docs",
        root_path=root,
        allowed_roots=[root],
    )
    first = await sync_local_directory(config, tenant_id="tenant-a", kb_id="support")
    second = await sync_local_directory(config, tenant_id="tenant-a", kb_id="support")

    assert (first.ingested, first.skipped, first.unchanged) == (1, 0, 0)
    assert (second.ingested, second.skipped, second.unchanged) == (0, 1, 1)
    assert len(database.execute("SELECT id FROM knowledge_documents").fetchall()) == 1
    assert len(database.execute("SELECT id FROM knowledge_chunks").fetchall()) == 1


async def test_removed_local_file_is_deleted_from_kb_and_search_results(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    document_path = root / "runbook.md"
    document_path.write_text("# Runbook\nUniqueDeletionNeedle", encoding="utf-8")

    from fleetent.intelligence.knowledge_base import search
    from fleetent.intelligence.knowledge_base.connectors import (
        LocalDirectorySourceConfig,
        sync_local_directory,
    )

    config = LocalDirectorySourceConfig(
        source_id="local-docs",
        root_path=root,
        allowed_roots=[root],
    )
    await sync_local_directory(config, tenant_id="tenant-a", kb_id="support")
    before = await search("UniqueDeletionNeedle", "tenant-a", ["support"], mode="keyword")

    document_path.unlink()
    summary = await sync_local_directory(config, tenant_id="tenant-a", kb_id="support")
    after = await search("UniqueDeletionNeedle", "tenant-a", ["support"], mode="keyword")

    assert len(before) == 1
    assert summary.deleted == 1
    assert summary.failed == 0
    assert after == []


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
    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    monkeypatch.setattr(runtime.vector_store, "delete", _noop_delete)
    return database


async def _noop_upsert(chunk_id: str, content: str, namespace: str) -> None:
    return None


async def _noop_delete(chunk_id: str, namespace: str) -> None:
    return None


async def _raise_if_called(*args, **kwargs):
    raise AssertionError("unexpected runtime mutation")
