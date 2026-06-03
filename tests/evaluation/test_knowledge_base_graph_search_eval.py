import json
from pathlib import Path

from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import create_database
from fleetent.intelligence.knowledge_base.parsers import ParsedDocument, ParsedSection
from tests.integration.test_migrations import apply_migrations

FIXTURE = Path("tests/evaluation/fixtures/knowledge_base_graph_search/basic.json")


async def test_graph_search_evaluation_fixture_covers_direct_relation_and_direction(
    monkeypatch,
    tmp_path,
):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    _patch_knowledge_runtime(monkeypatch, tmp_path)

    from fleetent.intelligence.knowledge_base import graph_search, run_entity_extraction, runtime

    document_ids: dict[str, str] = {}
    for item in payload["documents"]:
        document = await runtime.ingest_parsed(
            ParsedDocument(
                filename=f"{item['id']}.md",
                format="markdown",
                sections=[
                    ParsedSection(
                        title="body",
                        text=item["content"],
                        level=0,
                        metadata={"path": "body"},
                    )
                ],
                metadata={"filename": f"{item['id']}.md", "format": "markdown"},
            )
        )
        document_ids[item["id"]] = document.id
    await run_entity_extraction("default", "global")

    for case in payload["queries"]:
        result = await graph_search(case["query"], "default", ["global"], depth=case["depth"])
        actual = {chunk.chunk.document_id for chunk in result.chunks}
        expected = {document_ids[item] for item in case["expected_documents"]}
        forbidden = {document_ids[item] for item in case["forbidden_documents"]}
        assert expected <= actual
        assert actual.isdisjoint(forbidden)


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


async def _noop_upsert(chunk_id: str, content: str, namespace: str) -> None:
    return None


async def _noop_delete(chunk_id: str, namespace: str) -> None:
    return None
