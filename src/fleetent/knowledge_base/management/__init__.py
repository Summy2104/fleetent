"""Knowledge-base management layer package exports."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .runtime import (
        archive_knowledge_base,
        create_knowledge_base,
        is_active_knowledge_base,
        iter_indexable_chunks,
        list_documents,
        list_knowledge_bases,
        preview_document_chunks,
        update_knowledge_base_description,
    )


def __getattr__(name: str) -> object:
    if name == "management":
        # Keep `from fleetent.knowledge_base.management import management` working
        # as a compatibility shim import.
        return __import__(__name__, fromlist=["*"])
    if name == "runtime":
        return import_module("fleetent.knowledge_base.management.runtime")
    if name in {
        "archive_knowledge_base",
        "create_knowledge_base",
        "is_active_knowledge_base",
        "iter_indexable_chunks",
        "list_documents",
        "list_knowledge_bases",
        "preview_document_chunks",
        "update_knowledge_base_description",
    }:
        from .runtime import (
            archive_knowledge_base,
            create_knowledge_base,
            is_active_knowledge_base,
            iter_indexable_chunks,
            list_documents,
            list_knowledge_bases,
            preview_document_chunks,
            update_knowledge_base_description,
        )

        return {
            "archive_knowledge_base": archive_knowledge_base,
            "create_knowledge_base": create_knowledge_base,
            "is_active_knowledge_base": is_active_knowledge_base,
            "iter_indexable_chunks": iter_indexable_chunks,
            "list_documents": list_documents,
            "list_knowledge_bases": list_knowledge_bases,
            "preview_document_chunks": preview_document_chunks,
            "update_knowledge_base_description": update_knowledge_base_description,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(
        [
            *globals(),
            "management",
            "runtime",
            "archive_knowledge_base",
            "create_knowledge_base",
            "is_active_knowledge_base",
            "iter_indexable_chunks",
            "list_documents",
            "list_knowledge_bases",
            "preview_document_chunks",
            "update_knowledge_base_description",
        ]
    )


__all__ = [
    "archive_knowledge_base",
    "create_knowledge_base",
    "is_active_knowledge_base",
    "iter_indexable_chunks",
    "list_documents",
    "list_knowledge_bases",
    "preview_document_chunks",
    "update_knowledge_base_description",
]
