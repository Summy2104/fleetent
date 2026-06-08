"""Backward-compatible shim for legacy graph search imports."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


_GRAPH_SEARCH_EXPORTS = {
    "EntityRef",
    "GraphSearchChunk",
    "GraphSearchReason",
    "GraphSearchResult",
    "RelationRef",
    "_add_candidate",
    "_direct_mention_chunk_ids",
    "_entities_by_id",
    "_metadata_aliases",
    "_relations_for_entities",
    "_related_entity_ids",
    "_dedupe_entities",
    "_dedupe_relations",
    "graph_search",
    "match_entities",
}


def _graph_search_module() -> object:
    from fleetent.knowledge_base.retrieval import graph_search as module

    return module


def __getattr__(name: str) -> object:
    if name in _GRAPH_SEARCH_EXPORTS:
        return getattr(_graph_search_module(), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted([*globals(), *_GRAPH_SEARCH_EXPORTS])


__all__ = sorted(_GRAPH_SEARCH_EXPORTS)
