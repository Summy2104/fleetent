def test_knowledge_base_public_api_is_importable():
    from fleetent.intelligence.knowledge_base import (
        KnowledgeChunk,
        KnowledgeDocument,
        delete,
        ingest_text,
        search,
    )

    assert KnowledgeDocument is not None
    assert KnowledgeChunk is not None
    assert callable(ingest_text)
    assert callable(search)
    assert callable(delete)
