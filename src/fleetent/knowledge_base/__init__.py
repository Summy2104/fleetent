"""Compatibility-focused top-level API for knowledge-base features."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import core, ingest, management, retrieval
    from .core import (
        KnowledgeChunk,
        KnowledgeDocument,
        KnowledgeReadable,
        KnowledgeStore,
        KnowledgeWritable,
    )


def __getattr__(name: str) -> object:
    if name in {"core", "ingest", "management", "retrieval"}:
        return import_module(f"fleetent.knowledge_base.{name}")
    if name in {
        "KnowledgeChunk",
        "KnowledgeDocument",
        "KnowledgeReadable",
        "KnowledgeStore",
        "KnowledgeWritable",
        "iter_indexable_knowledge_chunks",
    }:
        from .core import (
            KnowledgeChunk,
            KnowledgeDocument,
            KnowledgeReadable,
            KnowledgeStore,
            KnowledgeWritable,
        )
        from .ingest.runtime import iter_indexable_knowledge_chunks

        return {
            "KnowledgeChunk": KnowledgeChunk,
            "KnowledgeDocument": KnowledgeDocument,
            "KnowledgeReadable": KnowledgeReadable,
            "KnowledgeStore": KnowledgeStore,
            "KnowledgeWritable": KnowledgeWritable,
            "iter_indexable_knowledge_chunks": iter_indexable_knowledge_chunks,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(
        [
            *globals(),
            "core",
            "ingest",
            "management",
            "retrieval",
            "KnowledgeChunk",
            "KnowledgeDocument",
            "KnowledgeReadable",
            "KnowledgeStore",
            "KnowledgeWritable",
            "iter_indexable_knowledge_chunks",
        ]
    )


__all__ = [
    "core",
    "ingest",
    "management",
    "retrieval",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeReadable",
    "KnowledgeStore",
    "KnowledgeWritable",
    "iter_indexable_knowledge_chunks",
]
