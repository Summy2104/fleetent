from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import create_database
from tests.integration.test_migrations import apply_migrations


def _patch_runtime_database(monkeypatch, tmp_path):
    from fleetent.intelligence.knowledge_base import runtime

    db_path = tmp_path / "knowledge.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(runtime, "_database", lambda: database)
    return database


def _patch_runtime_settings(monkeypatch, **knowledge_base):
    from fleetent.intelligence.knowledge_base import runtime

    settings = Settings(
        anthropic_api_key="test-key",
        knowledge_base=KnowledgeBaseSettings(**knowledge_base),
    )
    monkeypatch.setattr(runtime, "_settings", lambda: settings)


async def _noop_upsert(chunk_id: str, content: str, namespace: str) -> None:
    return None


async def test_iter_indexable_knowledge_chunks_returns_tenant_kb_chunks(tmp_path, monkeypatch):
    from fleetent.intelligence.knowledge_base import iter_indexable_knowledge_chunks, runtime

    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=20, chunk_overlap=0)
    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    document = await runtime.ingest_text(
        filename="guide.txt",
        content="tenant handbook",
        tenant_id="tenant-a",
        kb_id="global",
    )
    await runtime.ingest_text(
        filename="other.txt",
        content="other handbook",
        tenant_id="tenant-b",
        kb_id="global",
    )

    items = list(iter_indexable_knowledge_chunks("tenant-a", "global"))

    assert [(item.id, item.content, item.namespace) for item in items] == [
        (f"{document.id}:chunk:0", "tenant handbook", "kb:tenant-a:global")
    ]


async def test_iter_indexable_knowledge_chunks_excludes_other_kbs(tmp_path, monkeypatch):
    from fleetent.intelligence.knowledge_base import iter_indexable_knowledge_chunks, runtime

    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=20, chunk_overlap=0)
    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    handbook = await runtime.ingest_text(
        filename="handbook.txt",
        content="team handbook",
        tenant_id="tenant-a",
        kb_id="handbook",
    )
    await runtime.ingest_text(
        filename="runbook.txt",
        content="team runbook",
        tenant_id="tenant-a",
        kb_id="runbook",
    )

    items = list(iter_indexable_knowledge_chunks("tenant-a", "handbook"))

    assert [(item.id, item.content, item.namespace) for item in items] == [
        (f"{handbook.id}:chunk:0", "team handbook", "kb:tenant-a:handbook")
    ]
