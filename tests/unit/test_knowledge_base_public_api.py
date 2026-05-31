import inspect

import pytest


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


def test_search_accepts_search_mode_with_vector_default():
    from fleetent.intelligence.knowledge_base import search

    signature = inspect.signature(search)

    assert signature.parameters["mode"].default == "vector"


async def test_search_rejects_unsupported_mode_before_backend_access():
    from fleetent.intelligence.knowledge_base import search

    with pytest.raises(ValueError, match="unsupported knowledge search mode: graph"):
        await search("query", mode="graph")
