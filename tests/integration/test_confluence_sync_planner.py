from __future__ import annotations

from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import create_database
from tests.integration.test_migrations import apply_migrations


async def test_new_confluence_page_is_planned_for_ingest(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import SyncAction
    from fleetent.knowledge_base.connectors.confluence import (
        FakeConfluenceClient,
        plan_confluence_sync,
    )

    plan = await plan_confluence_sync(
        _config(),
        client=FakeConfluenceClient(space_pages={"ENG": [[_page("1", "Runbook")]]}),
    )

    assert [item.action for item in plan.items] == [SyncAction.INGEST_NEW]
    assert plan.items[0].source_path == "confluence://1"
    assert plan.summary.ingested == 1


async def test_changed_confluence_page_is_planned_for_reingest(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import SyncAction
    from fleetent.knowledge_base.connectors import (
        LocalSourceState,
        LocalSourceStateStore,
    )
    from fleetent.knowledge_base.connectors.confluence import (
        FakeConfluenceClient,
        confluence_fingerprint,
        plan_confluence_sync,
    )

    old_page = _page("1", "Runbook", version=1)
    LocalSourceStateStore(database).upsert(
        LocalSourceState(
            source_id="conf-eng",
            tenant_id="tenant-a",
            kb_id="engineering",
            source_path="confluence://1",
            mtime_ns=1,
            content_hash=confluence_fingerprint(old_page),
            document_id="kb-doc-1",
        )
    )

    plan = await plan_confluence_sync(
        _config(),
        client=FakeConfluenceClient(space_pages={"ENG": [[_page("1", "Runbook", version=2)]]}),
    )

    assert [item.action for item in plan.items] == [SyncAction.REINGEST_CHANGED]
    assert plan.items[0].document_id == "kb-doc-1"
    assert plan.summary.changed == 1


async def test_unchanged_confluence_page_is_planned_for_skip(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import SyncAction
    from fleetent.knowledge_base.connectors import (
        LocalSourceState,
        LocalSourceStateStore,
    )
    from fleetent.knowledge_base.connectors.confluence import (
        FakeConfluenceClient,
        _modified_time_ns,
        confluence_fingerprint,
        plan_confluence_sync,
    )

    page = _page("1", "Runbook", version=1)
    LocalSourceStateStore(database).upsert(
        LocalSourceState(
            source_id="conf-eng",
            tenant_id="tenant-a",
            kb_id="engineering",
            source_path="confluence://1",
            mtime_ns=_modified_time_ns(page),
            content_hash=confluence_fingerprint(page),
            document_id="kb-doc-1",
        )
    )

    plan = await plan_confluence_sync(
        _config(),
        client=FakeConfluenceClient(space_pages={"ENG": [[page]]}),
    )

    assert [item.action for item in plan.items] == [SyncAction.SKIP_UNCHANGED]
    assert plan.summary.unchanged == 1


async def test_missing_confluence_source_state_is_planned_for_archive(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    from fleetent.knowledge_base import SyncAction
    from fleetent.knowledge_base.connectors import (
        LocalSourceState,
        LocalSourceStateStore,
    )
    from fleetent.knowledge_base.connectors.confluence import (
        FakeConfluenceClient,
        plan_confluence_sync,
    )

    LocalSourceStateStore(database).upsert(
        LocalSourceState(
            source_id="conf-eng",
            tenant_id="tenant-a",
            kb_id="engineering",
            source_path="confluence://missing",
            mtime_ns=1,
            content_hash="old",
            document_id="kb-doc-1",
        )
    )

    plan = await plan_confluence_sync(
        _config(),
        client=FakeConfluenceClient(space_pages={"ENG": [[]]}),
    )

    assert [item.action for item in plan.items] == [SyncAction.ARCHIVE_MISSING]
    assert plan.items[0].document_id == "kb-doc-1"
    assert plan.summary.archived == 1


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


def _page(page_id: str, title: str, *, version: int = 1):
    from fleetent.knowledge_base.connectors.confluence import ConfluencePage

    return ConfluencePage(
        id=page_id,
        title=title,
        space_key="ENG",
        storage_html=f"<h1>{title}</h1><p>Body</p>",
        version=version,
        modified_time="2026-06-02T00:00:00+00:00",
        ancestors=["Engineering"],
    )


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
    return database
