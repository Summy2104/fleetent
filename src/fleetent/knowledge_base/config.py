"""Compatibility facade for legacy knowledge-base configuration imports."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


_EXPORTS = (
    "KnowledgeBaseConfig",
    "KnowledgeConfigSnapshot",
    "KnowledgeIndexingConfig",
    "KnowledgeSourceConfig",
    "KnowledgeSyncConfig",
    "SourceType",
    "load_knowledge_config",
    "knowledge_config_path",
)


def _legacy_module() -> Any:
    return import_module("fleetent.intelligence.knowledge_base.config")


def __getattr__(name: str) -> object:
    if name in _EXPORTS:
        return getattr(_legacy_module(), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted([*globals(), *_EXPORTS])


__all__ = list(_EXPORTS)
