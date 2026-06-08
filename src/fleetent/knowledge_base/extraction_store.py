"""Compatibility facade for legacy knowledge-base extraction store imports."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fleetent.intelligence.knowledge_base.extraction_store import (  # noqa: F401
        KnowledgeEntity,
        KnowledgeEntityStore,
        KnowledgeExtractionRun,
    )


def _legacy_module() -> Any:
    return import_module("fleetent.intelligence.knowledge_base.extraction_store")


def __getattr__(name: str) -> object:
    module = _legacy_module()
    try:
        return getattr(module, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc


def __dir__() -> list[str]:
    return sorted(
        {
            *globals(),
            *[name for name in dir(_legacy_module()) if not name.startswith("_")],
        }
    )
