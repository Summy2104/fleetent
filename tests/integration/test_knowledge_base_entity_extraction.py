from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import create_database
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.knowledge_base.parsers import ParsedDocument, ParsedSection
from fleetent.schema_migrations import migrate


async def test_run_entity_extraction_document_scope_writes_summary_entities_and_evidence(
    monkeypatch,
    tmp_path,
):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    document = await _ingest_fixture_document(
        filename="runbook.md",
        content=(
            "Customer: Acme\n"
            "Project: Atlas\n"
            "System: Billing API\n"
            "Depends on: Billing API -> Data Warehouse"
        ),
    )

    from fleetent.knowledge_base import run_entity_extraction

    summary = await run_entity_extraction("default", "global", document_id=document.id)

    entities = database.execute("SELECT entity_type, name FROM kb_entities ORDER BY name")
    mentions = database.execute("SELECT document_id, chunk_id, text FROM kb_entity_mentions")
    relations = database.execute(
        """
        SELECT relation_type, evidence_document_id, evidence_chunk_id, evidence_text
        FROM kb_relations
        """
    )
    tables = _table_names(database)
    mention_columns = _column_names(database, "kb_entity_mentions")
    relation_columns = _column_names(database, "kb_relations")
    assert summary.status == "succeeded"
    assert summary.documents_scanned == 1
    assert summary.chunks_scanned == 1
    assert summary.entities_upserted >= 4
    assert summary.mentions_written >= 3
    assert summary.relations_written == 1
    assert "kb_extraction_runs" not in tables
    assert "extraction_run_id" not in mention_columns
    assert "extraction_run_id" not in relation_columns
    assert {(row["entity_type"], row["name"]) for row in entities.fetchall()} >= {
        ("customer", "Acme"),
        ("project", "Atlas"),
        ("system", "Billing API"),
        ("system", "Data Warehouse"),
    }
    assert len(mentions.fetchall()) >= 3
    relation = relations.fetchone()
    assert relation["relation_type"] == "depends_on"
    assert relation["evidence_document_id"] == document.id
    assert relation["evidence_chunk_id"].endswith(":chunk:0")
    assert relation["evidence_text"] == "Depends on: Billing API -> Data Warehouse"


async def test_run_entity_extraction_kb_scope_isolates_document_failures(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    good = await _ingest_fixture_document("good.md", "Customer: Acme")
    bad = await _ingest_fixture_document("bad.md", "Customer: Broken")

    from fleetent.knowledge_base import extraction, run_entity_extraction

    original = extraction.deterministic_extract

    def fail_one_document(text: str, document_id: str, chunk_id: str):
        if document_id == bad.id:
            raise ValueError("fixture failure with secret body")
        return original(text, document_id, chunk_id)

    monkeypatch.setattr(extraction, "deterministic_extract", fail_one_document)

    summary = await run_entity_extraction("default", "global")

    mentions = database.execute("SELECT DISTINCT document_id FROM kb_entity_mentions")
    assert summary.status == "partial_failed"
    assert summary.documents_scanned == 2
    assert summary.failed_count == 1
    assert [row["document_id"] for row in mentions.fetchall()] == [good.id]


async def test_successful_document_rerun_replaces_old_evidence(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    document = await _ingest_fixture_document("runbook.md", "Customer: Acme")

    from fleetent.knowledge_base import run_entity_extraction

    first = await run_entity_extraction("default", "global", document_id=document.id)
    await _replace_document_chunk(database, document.id, "Customer: Beta")
    second = await run_entity_extraction("default", "global", document_id=document.id)

    entity_names = database.execute("SELECT name FROM kb_entities ORDER BY name").fetchall()
    mentions = database.execute("SELECT text FROM kb_entity_mentions ORDER BY text").fetchall()
    assert first.status == "succeeded"
    assert second.status == "succeeded"
    assert [row["name"] for row in entity_names] == ["Acme", "Beta"]
    assert [row["text"] for row in mentions] == ["Beta"]
    assert first.id != second.id


async def test_failed_document_rerun_keeps_previous_evidence(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    document = await _ingest_fixture_document("runbook.md", "Customer: Acme")

    from fleetent.knowledge_base import extraction, run_entity_extraction

    await run_entity_extraction("default", "global", document_id=document.id)

    def fail_extractor(text: str, document_id: str, chunk_id: str):
        raise ValueError("bad extraction secret content")

    monkeypatch.setattr(extraction, "deterministic_extract", fail_extractor)

    summary = await run_entity_extraction("default", "global", document_id=document.id)

    mentions = database.execute("SELECT text FROM kb_entity_mentions").fetchall()
    assert summary.status == "failed"
    assert [row["text"] for row in mentions] == ["Acme"]
    assert summary.error_summary == "ValueError"


async def _ingest_fixture_document(filename: str, content: str):
    from fleetent.knowledge_base import runtime

    return await runtime.ingest_parsed(
        ParsedDocument(
            filename=filename,
            format="markdown",
            sections=[
                ParsedSection(title="body", text=content, level=0, metadata={"path": "body"})
            ],
            metadata={"filename": filename, "format": "markdown"},
        )
    )


async def _replace_document_chunk(database, document_id: str, content: str) -> None:
    database.execute(
        """
        UPDATE knowledge_chunks
        SET content = :content
        WHERE document_id = :document_id
        """,
        {"content": content, "document_id": document_id},
    )
    database.execute(
        """
        UPDATE knowledge_chunks_fts
        SET content = :content
        WHERE chunk_id IN (
            SELECT id FROM knowledge_chunks WHERE document_id = :document_id
        )
        """,
        {"content": content, "document_id": document_id},
    )


def _patch_knowledge_runtime(monkeypatch, tmp_path):
    from fleetent.db import SQLiteDatabase
    from fleetent.knowledge_base import runtime

    db_path = tmp_path / "knowledge.db"
    migrate(SQLiteDatabase(path=db_path), KB_MIGRATIONS)
    database = create_database(f"sqlite:///{db_path}")
    settings = Settings(
        anthropic_api_key="test-key",
        knowledge_base=KnowledgeBaseSettings(chunk_size=500, chunk_overlap=0),
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


def _table_names(database) -> set[str]:
    return {
        str(row["name"])
        for row in database.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def _column_names(database, table: str) -> set[str]:
    return {str(row["name"]) for row in database.execute(f"PRAGMA table_info({table})").fetchall()}
