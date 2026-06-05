import inspect

import pytest


def test_knowledge_base_public_api_is_importable():
    from fleetent.intelligence.knowledge_base import (
        EntityRef,
        ExtractedEntity,
        ExtractedRelation,
        ExtractionResult,
        GraphSearchChunk,
        GraphSearchResult,
        KnowledgeChunk,
        KnowledgeConfigSnapshot,
        KnowledgeDocument,
        KnowledgeEntity,
        KnowledgeExtractionRun,
        KnowledgeSourceConfig,
        ParsedDocument,
        ParsedSection,
        delete,
        graph_search,
        ingest_parsed,
        ingest_text,
        parse_document,
        parse_docx,
        parse_html,
        parse_markdown,
        parse_pdf,
        parse_pptx,
        parse_text,
        parse_xlsx,
        run_entity_extraction,
        search,
    )

    assert ExtractedEntity is not None
    assert ExtractedRelation is not None
    assert ExtractionResult is not None
    assert EntityRef is not None
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
    from fleetent.intelligence.knowledge_base import ParsedDocument, ParsedSection, parse_text

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
    from fleetent.intelligence.knowledge_base import search

    signature = inspect.signature(search)

    assert signature.parameters["mode"].default == "vector"


async def test_search_rejects_unsupported_mode_before_backend_access():
    from fleetent.intelligence.knowledge_base import search

    with pytest.raises(ValueError, match="unsupported knowledge search mode: graph"):
        await search("query", mode="graph")
