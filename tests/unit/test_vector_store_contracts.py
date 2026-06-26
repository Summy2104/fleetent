import ast
import importlib
from pathlib import Path

import pytest

_EXPECTED_PUBLIC_SYMBOLS = {
    "IndexableItem",
    "ReindexRequest",
    "ReindexSummary",
    "RerankProvider",
    "RerankProviderError",
    "RerankResult",
    "SearchResult",
    "clear_namespace",
    "configure_from_active_agent",
    "create_rerank_provider",
    "delete",
    "knowledge_namespace",
    "memory_namespace",
    "reindex",
    "search",
    "upsert",
}


_BANNED_SUBSTRINGS = (
    "fleetent.platform",
    "fleetent.knowledge_base",
    "fleetent.memory",
)


def test_vector_store_top_level_package_exports_original_api():
    module = importlib.import_module("fleetent.vector_store")

    assert module.__file__ is not None
    for symbol in sorted(_EXPECTED_PUBLIC_SYMBOLS):
        assert hasattr(module, symbol), f"missing public symbol: {symbol}"


def test_vector_store_no_platform_or_intelligence_cross_imports():
    package = importlib.import_module("fleetent.vector_store")
    package_dir = Path(package.__file__).resolve().parent

    for path in package_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and any(node.module.startswith(prefix) for prefix in _BANNED_SUBSTRINGS)
            ):
                pytest.fail(f"vector_store import from banned module in {path}: {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name.startswith(prefix) for prefix in _BANNED_SUBSTRINGS):
                        pytest.fail(f"vector_store import banned module in {path}: {alias.name}")

    assert package.__name__ == "fleetent.vector_store"
