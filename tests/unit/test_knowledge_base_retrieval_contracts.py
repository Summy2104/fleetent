import inspect


def test_retrieval_search_functions_accept_readable_store() -> None:
    from fleetent.knowledge_base.retrieval import graph_search, scope, search

    search_sig = inspect.signature(search.search)
    graph_sig = inspect.signature(graph_search.graph_search)
    scope_sig = inspect.signature(scope.resolve_agent_kb_ids)
    assert "KnowledgeReadable" in str(search_sig.parameters["store"].annotation)
    assert "KnowledgeReadable" in str(graph_sig.parameters["store"].annotation)
    # 3rd param is optional `database` for test injection; public call-site contract unchanged
    assert len(scope_sig.parameters) == 3


def test_retrieval_modules_do_not_reference_writes() -> None:
    from fleetent.knowledge_base.retrieval import graph_search, scope, search

    for module in (graph_search, scope, search):
        source = inspect.getsource(module)
        assert "insert_document(" not in source
        assert "insert_chunks(" not in source
        assert "update_knowledge_base_description(" not in source
        assert "archive_knowledge_base(" not in source
        assert "delete_document(" not in source
        assert "delete_scoped_document(" not in source
