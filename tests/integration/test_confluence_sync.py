from __future__ import annotations

from unittest.mock import AsyncMock

from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.schema_migrations import migrate


async def test_confluence_sync_ingests_pages_into_tenant_kb(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import sync_confluence
    from fleetent.knowledge_base.connectors.confluence import FakeConfluenceClient

    summary = await sync_confluence(
        _config(),
        client=FakeConfluenceClient(space_pages={"ENG": [[_page("1", "Runbook")]]}),
    )

    documents = database.execute(
        "SELECT tenant_id, kb_id, filename, source, source_url FROM knowledge_documents"
    ).fetchall()
    chunks = database.execute("SELECT content FROM knowledge_chunks").fetchall()

    assert summary.scanned == 1
    assert summary.ingested == 1
    assert documents == [
        {
            "tenant_id": "tenant-a",
            "kb_id": "engineering",
            "filename": "Runbook.html",
            "source": "confluence:conf-eng",
            "source_url": "confluence://1",
        }
    ]
    assert chunks == [{"content": "Body"}]


async def test_confluence_reingest_changed_replaces_old_document(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import sync_confluence
    from fleetent.knowledge_base.connectors.confluence import FakeConfluenceClient

    first = await sync_confluence(
        _config(),
        client=FakeConfluenceClient(space_pages={"ENG": [[_page("1", "Runbook", version=1)]]}),
    )
    second = await sync_confluence(
        _config(),
        client=FakeConfluenceClient(
            space_pages={"ENG": [[_page("1", "Runbook", version=2, body="Second")]]}
        ),
    )

    documents = database.execute("SELECT id, filename FROM knowledge_documents").fetchall()
    chunks = database.execute("SELECT content FROM knowledge_chunks").fetchall()

    assert first.ingested == 1
    assert second.changed == 1
    assert second.ingested == 1
    assert len(documents) == 1
    assert chunks == [{"content": "Second"}]


async def test_confluence_archive_missing_does_not_call_physical_delete(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import runtime, sync_confluence
    from fleetent.knowledge_base.connectors.confluence import FakeConfluenceClient

    await sync_confluence(
        _config(),
        client=FakeConfluenceClient(space_pages={"ENG": [[_page("1", "Runbook")]]}),
    )
    delete = AsyncMock()
    monkeypatch.setattr(runtime, "delete", delete)

    summary = await sync_confluence(
        _config(),
        client=FakeConfluenceClient(space_pages={"ENG": [[]]}),
    )

    documents = database.execute("SELECT filename, archived_at FROM knowledge_documents").fetchall()
    chunks = database.execute("SELECT content FROM knowledge_chunks").fetchall()

    assert summary.archived == 1
    delete.assert_not_awaited()
    assert documents[0]["archived_at"] is not None
    assert chunks == []


async def test_confluence_item_failure_does_not_block_following_items(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import sync_confluence
    from fleetent.knowledge_base.connectors.confluence import FakeConfluenceClient

    summary = await sync_confluence(
        _config(),
        client=FakeConfluenceClient(
            space_pages={
                "ENG": [
                    [
                        _page("bad", "Bad", body=""),
                        _page("good", "Good", body="Still ingested"),
                    ]
                ]
            }
        ),
    )

    assert summary.failed == 1
    assert summary.ingested == 1


async def test_sync_confluence_uses_plan_then_executor(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import sync_confluence
    from fleetent.knowledge_base.connectors.confluence import (
        ConfluenceSyncPlan,
        FakeConfluenceClient,
    )

    calls: list[str] = []

    async def fake_plan(config, *, client):
        calls.append("plan")
        return ConfluenceSyncPlan(config=config, items=[], pages={}, summary=_empty_summary())

    async def fake_execute(plan, *, client):
        calls.append("execute")
        return _execution_summary()

    monkeypatch.setattr(
        "fleetent.knowledge_base.connectors.confluence.plan_confluence_sync",
        fake_plan,
    )
    monkeypatch.setattr(
        "fleetent.knowledge_base.connectors.confluence.execute_confluence_sync_plan",
        fake_execute,
    )

    summary = await sync_confluence(_config(), client=FakeConfluenceClient())

    assert calls == ["plan", "execute"]
    assert summary.scanned == 0


def _config():
    from fleetent.knowledge_base import ConfluenceConnectorConfig

    return ConfluenceConnectorConfig(
        connector_id="conf-eng",
        tenant_id="tenant-a",
        kb_id="engineering",
        base_url="https://example.atlassian.net/wiki",
        username="bot@example.com",
        credential_ref="env:CONFLUENCE_TOKEN",
        scope_type="space",
        space_key="ENG",
    )


def _page(page_id: str, title: str, *, version: int = 1, body: str = "Body"):
    from fleetent.knowledge_base.connectors.confluence import ConfluencePage

    return ConfluencePage(
        id=page_id,
        title=title,
        space_key="ENG",
        storage_html=f"<h1>{title}</h1><p>{body}</p>",
        version=version,
        modified_time="2026-06-02T00:00:00+00:00",
        ancestors=["Engineering"],
    )


def _empty_summary():
    from fleetent.knowledge_base import SyncPlanSummary

    return SyncPlanSummary(scanned=0, planned=0)


def _execution_summary():
    from fleetent.knowledge_base.connectors.confluence import ConfluenceSyncSummary

    return ConfluenceSyncSummary(scanned=0, planned=0)


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
    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    monkeypatch.setattr(runtime.vector_store, "delete", _noop_delete)
    return database


async def _noop_upsert(chunk_id: str, content: str, namespace: str) -> None:
    return None


async def _noop_delete(chunk_id: str, namespace: str) -> None:
    return None
