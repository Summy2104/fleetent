"""Guardrails for KB routing injection.

The KB read/write path for this change must not self-connect to the global
management DB or bypass the injected per-tenant vector backend.
"""

from __future__ import annotations

from pathlib import Path

_KB_ROOT = Path("src/fleetent/knowledge_base")


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_runtime_has_no_settings_database_fallback() -> None:
    source = _source(_KB_ROOT / "runtime.py")
    assert "create_database(" not in source
    assert "Settings().database_url" not in source


def test_operations_has_no_default_database_bypass() -> None:
    source = _source(_KB_ROOT / "operations.py")
    assert "default_database(" not in source


def test_graph_search_has_no_settings_database_fallback() -> None:
    source = _source(_KB_ROOT / "retrieval" / "graph_search.py")
    assert "create_database(" not in source
    assert "Settings().database_url" not in source


def test_search_has_no_global_vector_search_bypass() -> None:
    source = _source(_KB_ROOT / "retrieval" / "search.py")
    assert "vector_store.search(" not in source
