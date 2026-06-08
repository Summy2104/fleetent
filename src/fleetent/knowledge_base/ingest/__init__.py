"""KB ingest layer public API and compatibility helpers."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import as_knowledge_base_settings
    from .runtime import (
        archive,
        delete,
        delete_document,
        ingest_parsed,
        ingest_text,
        iter_indexable_knowledge_chunks,
    )


def __getattr__(name: str) -> object:
    if name == "runtime":
        return import_module("fleetent.knowledge_base.ingest.runtime")
    if name in {
        "archive",
        "delete",
        "delete_document",
        "ingest_parsed",
        "ingest_text",
        "iter_indexable_knowledge_chunks",
    }:
        from .runtime import (
            archive,
            delete,
            delete_document,
            ingest_parsed,
            ingest_text,
            iter_indexable_knowledge_chunks,
        )

        return {
            "archive": archive,
            "delete": delete,
            "delete_document": delete_document,
            "ingest_parsed": ingest_parsed,
            "ingest_text": ingest_text,
            "iter_indexable_knowledge_chunks": iter_indexable_knowledge_chunks,
        }[name]
    if name == "as_knowledge_base_settings":
        from .config import as_knowledge_base_settings

        return as_knowledge_base_settings
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(
        [
            *globals(),
            "runtime",
            "as_knowledge_base_settings",
            "archive",
            "delete",
            "delete_document",
            "ingest_parsed",
            "ingest_text",
            "iter_indexable_knowledge_chunks",
        ]
    )


__all__ = [
    "archive",
    "as_knowledge_base_settings",
    "delete",
    "delete_document",
    "ingest_parsed",
    "ingest_text",
    "iter_indexable_knowledge_chunks",
]
