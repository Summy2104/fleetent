import inspect

import pytest


def test_retrieval_search_functions_accept_readable_store() -> None:
    from fleetent.knowledge_base.retrieval import graph_search, search

    search_sig = inspect.signature(search.search)
    graph_sig = inspect.signature(graph_search.graph_search)
    assert "KnowledgeReadable" in str(search_sig.parameters["store"].annotation)
    assert "KnowledgeReadable" in str(graph_sig.parameters["store"].annotation)


def test_dead_agent_kb_binding_symbols_are_not_exported() -> None:
    import fleetent.knowledge_base as knowledge_base
    import fleetent.knowledge_base.retrieval as retrieval

    resolver_name = "resolve_agent_kb_ids"
    for module, name in (
        (knowledge_base, "AgentKnowledgeBaseBinding"),
        (knowledge_base, "list_agent_kb_bindings"),
        (knowledge_base, resolver_name),
        (retrieval, "AgentKnowledgeBaseBinding"),
        (retrieval, resolver_name),
        (retrieval, "scope"),
    ):
        with pytest.raises(AttributeError):
            getattr(module, name)


def test_retrieval_modules_do_not_reference_writes() -> None:
    from fleetent.knowledge_base.retrieval import graph_search, search

    for module in (graph_search, search):
        source = inspect.getsource(module)
        assert "insert_document(" not in source
        assert "insert_chunks(" not in source
        assert "update_knowledge_base_description(" not in source
        assert "archive_knowledge_base(" not in source
        assert "delete_document(" not in source
        assert "delete_scoped_document(" not in source
