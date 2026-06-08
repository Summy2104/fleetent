from unittest.mock import MagicMock


def test_knowledge_store_satisfies_readable_and_writable_protocols() -> None:
    from fleetent.knowledge_base.core import KnowledgeReadable, KnowledgeStore, KnowledgeWritable

    store = KnowledgeStore(MagicMock())
    assert isinstance(store, KnowledgeReadable)
    assert isinstance(store, KnowledgeWritable)


def test_knowledge_store_declares_public_protocol_methods() -> None:
    from fleetent.knowledge_base.core import KnowledgeReadable, KnowledgeStore, KnowledgeWritable

    readable_methods: set[str] = {
        member
        for member in dir(KnowledgeReadable)
        if not member.startswith("_") and callable(getattr(KnowledgeReadable, member, None))
    }
    writable_methods: set[str] = {
        member
        for member in dir(KnowledgeWritable)
        if not member.startswith("_") and callable(getattr(KnowledgeWritable, member, None))
    }

    for member in ("has_active_knowledge_base", "iter_indexable_chunks", "search_keyword"):
        assert member in readable_methods
        assert callable(getattr(KnowledgeStore, member, None))

    for member in ("ensure_knowledge_base", "insert_document", "insert_chunks"):
        assert member in writable_methods
        assert callable(getattr(KnowledgeStore, member, None))
