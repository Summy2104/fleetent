from fleetent import long_term_ctx
from fleetent.knowledge_base import KnowledgeChunk


def _chunk() -> KnowledgeChunk:
    return KnowledgeChunk(
        id="chunk-1",
        document_id="doc-1",
        tenant_id="tenant-a",
        kb_id="kb-1",
        filename="guide.md",
        content="Fleetent supports on-prem knowledge retrieval.",
        position=3,
        score=0.91,
        source="manual",
        source_url="https://kb.example/doc-1",
        metadata={"section": "deploy", "lang": "en"},
    )


def test_knowledge_chunk_wire_round_trip_preserves_all_fields() -> None:
    payload = long_term_ctx._knowledge_chunk_to_wire_dict(_chunk())

    assert payload == {
        "id": "chunk-1",
        "document_id": "doc-1",
        "tenant_id": "tenant-a",
        "kb_id": "kb-1",
        "filename": "guide.md",
        "content": "Fleetent supports on-prem knowledge retrieval.",
        "position": 3,
        "score": 0.91,
        "source": "manual",
        "source_url": "https://kb.example/doc-1",
        "metadata": {"section": "deploy", "lang": "en"},
    }

    restored = long_term_ctx._knowledge_chunk_from_wire_dict(payload)

    assert restored == _chunk()
