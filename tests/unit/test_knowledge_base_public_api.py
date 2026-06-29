import inspect

import pytest


def test_knowledge_base_public_api_is_importable():
    from fleetent.knowledge_base.config import KnowledgeConfigSnapshot, KnowledgeSourceConfig
    from fleetent.knowledge_base.core import KnowledgeChunk, KnowledgeDocument
    from fleetent.knowledge_base.extraction import (
        ExtractedEntity,
        ExtractedRelation,
        ExtractionResult,
        run_entity_extraction,
    )
    from fleetent.knowledge_base.extraction_store import KnowledgeEntity, KnowledgeExtractionRun
    from fleetent.knowledge_base.parsers import (
        ParsedDocument,
        ParsedSection,
        parse_document,
        parse_docx,
        parse_html,
        parse_markdown,
        parse_pdf,
        parse_pptx,
        parse_text,
        parse_xlsx,
    )
    from fleetent.knowledge_base.retrieval.graph_search import (
        EntityRef,
        GraphSearchChunk,
        GraphSearchResult,
        graph_search,
    )
    from fleetent.knowledge_base.runtime import delete, ingest_parsed, ingest_text, search

    assert EntityRef is not None

    assert ExtractedEntity is not None
    assert ExtractedRelation is not None
    assert ExtractionResult is not None
    assert GraphSearchChunk is not None
    assert GraphSearchResult is not None
    assert KnowledgeConfigSnapshot is not None
    assert KnowledgeSourceConfig is not None
    assert KnowledgeEntity is not None
    assert KnowledgeExtractionRun is not None
    assert KnowledgeDocument is not None
    assert KnowledgeChunk is not None
    assert ParsedDocument is not None
    assert ParsedSection is not None
    assert callable(ingest_text)
    assert callable(ingest_parsed)
    assert callable(parse_document)
    assert callable(parse_text)
    assert callable(parse_markdown)
    assert callable(parse_html)
    assert callable(parse_pdf)
    assert callable(parse_docx)
    assert callable(parse_pptx)
    assert callable(parse_xlsx)
    assert callable(graph_search)
    assert callable(run_entity_extraction)
    assert callable(search)
    assert callable(delete)


def test_parse_text_returns_parsed_document_shape():
    from fleetent.knowledge_base.parsers import ParsedDocument, ParsedSection, parse_text

    parsed = parse_text("notes.txt", "hello world")

    assert parsed == ParsedDocument(
        filename="notes.txt",
        format="text",
        sections=[
            ParsedSection(
                title="body",
                text="hello world",
                level=0,
                metadata={"path": "body"},
            )
        ],
        metadata={"filename": "notes.txt", "format": "text"},
    )


def test_search_accepts_search_mode_with_vector_default():
    from fleetent.knowledge_base.runtime import search

    signature = inspect.signature(search)

    assert signature.parameters["mode"].default == "vector"


async def test_search_rejects_unsupported_mode_before_backend_access():
    from fleetent.knowledge_base.runtime import search

    with pytest.raises(ValueError, match="unsupported knowledge search mode: graph"):
        await search("query", mode="graph")


def test_list_knowledge_bases_exposes_extraction_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.knowledge_base import runtime

    monkeypatch.setattr(
        runtime,
        "_list_knowledge_bases_impl",
        lambda tenant_id, database=None: [
            {
                "tenant_id": tenant_id,
                "kb_id": "support",
                "description": "Support handbook",
                "doc_count": 0,
                "chunk_count": 0,
                "last_import": None,
                "archived_at": None,
                "extraction_enabled": 1,
            }
        ],
    )
    monkeypatch.setattr(runtime, "_database", lambda: object())

    rows = runtime.list_knowledge_bases("tenant-a")

    assert rows == [
        {
            "tenant_id": "tenant-a",
            "kb_id": "support",
            "description": "Support handbook",
            "doc_count": 0,
            "chunk_count": 0,
            "last_import": None,
            "archived": False,
            "extraction_enabled": True,
        }
    ]
