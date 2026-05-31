def test_knowledge_base_public_api_is_importable():
    from fleetent.intelligence.knowledge_base import (
        KnowledgeChunk,
        KnowledgeDocument,
        ParsedDocument,
        ParsedSection,
        delete,
        ingest_parsed,
        ingest_text,
        parse_html,
        parse_markdown,
        parse_text,
        search,
    )

    assert KnowledgeDocument is not None
    assert KnowledgeChunk is not None
    assert ParsedDocument is not None
    assert ParsedSection is not None
    assert callable(ingest_text)
    assert callable(ingest_parsed)
    assert callable(parse_text)
    assert callable(parse_markdown)
    assert callable(parse_html)
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
