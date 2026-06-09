"""Guardrail tests for knowledge_base Protocol type-layer boundaries."""

import ast
import inspect
from pathlib import Path


def test_protocols_module_exists_at_canonical_path() -> None:
    """KnowledgeReadable/KnowledgeWritable SHALL be importable from core.protocols."""
    from fleetent.knowledge_base.core.protocols import KnowledgeReadable, KnowledgeWritable  # noqa: F401


def test_knowledge_store_satisfies_protocols_without_inheritance() -> None:
    """KnowledgeStore SHALL satisfy both protocols via structural typing, not inheritance."""
    from fleetent.knowledge_base.core.protocols import KnowledgeReadable, KnowledgeWritable
    from fleetent.knowledge_base.core.store import KnowledgeStore

    assert not any(
        b in (KnowledgeReadable, KnowledgeWritable) for b in KnowledgeStore.__bases__
    ), (
        "KnowledgeStore explicitly inherits from KnowledgeReadable or KnowledgeWritable; "
        "structural typing (typing.Protocol) satisfies both without inheritance"
    )

    from unittest.mock import MagicMock

    store = KnowledgeStore(MagicMock())
    assert isinstance(store, KnowledgeReadable), "KnowledgeStore must satisfy KnowledgeReadable"
    assert isinstance(store, KnowledgeWritable), "KnowledgeStore must satisfy KnowledgeWritable"


def test_knowledge_readable_has_no_write_methods() -> None:
    """KnowledgeReadable SHALL NOT expose write methods (upsert/delete/archive/insert)."""
    from fleetent.knowledge_base.core.protocols import KnowledgeReadable

    readable_attrs = {
        name for name in dir(KnowledgeReadable) if not name.startswith("_")
    }
    write_method_fragments = ("upsert", "delete", "archive", "insert", "update")
    for method_name in readable_attrs:
        for fragment in write_method_fragments:
            assert fragment not in method_name, (
                f"KnowledgeReadable exposes write method '{method_name}' "
                f"(contains '{fragment}'), violating read-only protocol boundary"
            )


def test_retrieval_functions_type_annotated_with_knowledge_readable() -> None:
    """retrieval/ functions that accept a store SHALL use KnowledgeReadable annotation."""
    from fleetent.knowledge_base.retrieval import graph_search, search

    search_sig = inspect.signature(search.search)
    graph_sig = inspect.signature(graph_search.graph_search)
    assert "KnowledgeReadable" in str(search_sig.parameters["store"].annotation)
    assert "KnowledgeReadable" in str(graph_sig.parameters["store"].annotation)


def test_protocols_module_uses_typing_protocol_not_abc() -> None:
    """KnowledgeReadable/KnowledgeWritable SHALL use typing.Protocol, not ABC inheritance."""
    import fleetent.knowledge_base.core.protocols as proto_module

    assert proto_module.__file__ is not None
    source = Path(proto_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)

    assert any("typing" in imp for imp in imports), (
        "protocols.py must import from typing (for typing.Protocol)"
    )
    assert not any("abc" in imp.lower() for imp in imports), (
        "protocols.py must not import from abc; use typing.Protocol for structural subtyping"
    )
