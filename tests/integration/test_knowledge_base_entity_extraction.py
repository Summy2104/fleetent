from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import create_database
from fleetent.intelligence.knowledge_base.parsers import ParsedDocument, ParsedSection
from tests.integration.test_migrations import apply_migrations


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

    from fleetent.intelligence.knowledge_base import run_entity_extraction

    summary = await run_entity_extraction("default", "global", document_id=document.id)

    runs = database.execute(
        "SELECT status, documents_scanned, chunks_scanned FROM kb_extraction_runs"
    )
    entities = database.execute("SELECT entity_type, name FROM kb_entities ORDER BY name")
    mentions = database.execute("SELECT document_id, chunk_id, text FROM kb_entity_mentions")
    relations = database.execute(
        """
        SELECT relation_type, evidence_document_id, evidence_chunk_id, evidence_text
        FROM kb_relations
        """
    )
    assert summary.status == "succeeded"
    assert summary.documents_scanned == 1
    assert runs.fetchall() == [{"status": "succeeded", "documents_scanned": 1, "chunks_scanned": 1}]
    assert {(row["entity_type"], row["name"]) for row in entities.fetchall()} >= {
        ("customer", "Acme"),
        ("project", "Atlas"),
        ("system", "Billing API"),
        ("system", "Data Warehouse"),
    }
    assert len(mentions.fetchall()) >= 4
    relation = relations.fetchone()
    assert relation["relation_type"] == "depends_on"
    assert relation["evidence_document_id"] == document.id
    assert relation["evidence_chunk_id"].endswith(":chunk:0")
    assert relation["evidence_text"] == "Depends on: Billing API -> Data Warehouse"


async def test_run_entity_extraction_kb_scope_isolates_document_failures(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    good = await _ingest_fixture_document("good.md", "Customer: Acme")
    bad = await _ingest_fixture_document("bad.md", "Customer: Broken")

    from fleetent.intelligence.knowledge_base import extraction, run_entity_extraction

    original = extraction.deterministic_extract

    def fail_one_document(text: str, document_id: str, chunk_id: str):
        if document_id == bad.id:
            raise ValueError("fixture failure with secret body")
        return original(text, document_id, chunk_id)

    monkeypatch.setattr(extraction, "deterministic_extract", fail_one_document)

    summary = await run_entity_extraction("default", "global")

    run = database.execute("SELECT status, documents_scanned, failed_count FROM kb_extraction_runs")
    mentions = database.execute("SELECT DISTINCT document_id FROM kb_entity_mentions")
    assert summary.status == "partial_failed"
    assert summary.failed_count == 1
    assert run.fetchone() == {
        "status": "partial_failed",
        "documents_scanned": 2,
        "failed_count": 1,
    }
    assert [row["document_id"] for row in mentions.fetchall()] == [good.id]


async def test_successful_document_rerun_replaces_old_evidence(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    document = await _ingest_fixture_document("runbook.md", "Customer: Acme")

    from fleetent.intelligence.knowledge_base import run_entity_extraction

    first = await run_entity_extraction("default", "global", document_id=document.id)
    await _replace_document_chunk(database, document.id, "Customer: Beta")
    second = await run_entity_extraction("default", "global", document_id=document.id)

    entity_names = database.execute("SELECT name FROM kb_entities ORDER BY name").fetchall()
    mentions = database.execute("SELECT text FROM kb_entity_mentions ORDER BY text").fetchall()
    runs = database.execute("SELECT id FROM kb_extraction_runs").fetchall()
    assert first.status == "succeeded"
    assert second.status == "succeeded"
    assert [row["name"] for row in entity_names] == ["Acme", "Beta"]
    assert [row["text"] for row in mentions] == ["Beta"]
    assert len(runs) == 2


async def test_failed_document_rerun_keeps_previous_evidence(monkeypatch, tmp_path):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    document = await _ingest_fixture_document("runbook.md", "Customer: Acme")

    from fleetent.intelligence.knowledge_base import extraction, run_entity_extraction

    await run_entity_extraction("default", "global", document_id=document.id)

    def fail_extractor(text: str, document_id: str, chunk_id: str):
        raise ValueError("bad extraction secret content")

    monkeypatch.setattr(extraction, "deterministic_extract", fail_extractor)

    summary = await run_entity_extraction("default", "global", document_id=document.id)

    mentions = database.execute("SELECT text FROM kb_entity_mentions").fetchall()
    failed_run = database.execute(
        "SELECT status, error_summary FROM kb_extraction_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    assert summary.status == "failed"
    assert [row["text"] for row in mentions] == ["Acme"]
    assert failed_run["status"] == "failed"
    assert "secret content" not in failed_run["error_summary"]


async def _ingest_fixture_document(filename: str, content: str):
    from fleetent.intelligence.knowledge_base import runtime

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
    from fleetent.intelligence.knowledge_base import runtime

    db_path = tmp_path / "knowledge.db"
    apply_migrations(db_path)
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
