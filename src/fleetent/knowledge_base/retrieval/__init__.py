"""Knowledge-base read-path APIs."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .graph_search import (
        EntityRef,
        GraphSearchChunk,
        GraphSearchReason,
        GraphSearchResult,
        RelationRef,
        match_entities,
    )
    from .scope import (
        AgentKnowledgeBaseBinding,
        resolve_agent_kb_ids,
    )
    from .search import SearchMode


def __getattr__(name: str) -> object:
    if name in {"graph_search", "search", "scope"}:
        return import_module(f"fleetent.knowledge_base.retrieval.{name}")
    if name in {
        "AgentKnowledgeBaseBinding",
        "resolve_agent_kb_ids",
    }:
        from .scope import AgentKnowledgeBaseBinding, resolve_agent_kb_ids

        return {
            "AgentKnowledgeBaseBinding": AgentKnowledgeBaseBinding,
            "resolve_agent_kb_ids": resolve_agent_kb_ids,
        }[name]
    if name in {"SearchMode", "_search_hybrid", "_search_vector"}:
        from .search import SearchMode, _search_hybrid, _search_vector

        return {
            "SearchMode": SearchMode,
            "_search_hybrid": _search_hybrid,
            "_search_vector": _search_vector,
        }[name]
    if name in {
        "GraphSearchChunk",
        "GraphSearchReason",
        "GraphSearchResult",
        "RelationRef",
        "EntityRef",
        "match_entities",
        "_entities_by_id",
    }:
        from .graph_search import (
            EntityRef,
            GraphSearchChunk,
            GraphSearchReason,
            GraphSearchResult,
            RelationRef,
            match_entities,
        )

        return {
            "GraphSearchChunk": GraphSearchChunk,
            "GraphSearchReason": GraphSearchReason,
            "GraphSearchResult": GraphSearchResult,
            "RelationRef": RelationRef,
            "EntityRef": EntityRef,
            "match_entities": match_entities,
        }[name]
    if name in {
        "_rerank_candidate_limit",
        "_rerank_hybrid_candidates",
        "_apply_rerank_results",
    }:
        from .search import (
            _apply_rerank_results,
            _rerank_candidate_limit,
            _rerank_hybrid_candidates,
        )

        return {
            "_rerank_candidate_limit": _rerank_candidate_limit,
            "_rerank_hybrid_candidates": _rerank_hybrid_candidates,
            "_apply_rerank_results": _apply_rerank_results,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(
        [
            *globals(),
            "AgentKnowledgeBaseBinding",
            "EntityRef",
            "GraphSearchChunk",
            "GraphSearchReason",
            "GraphSearchResult",
            "RelationRef",
            "SearchMode",
            "resolve_agent_kb_ids",
            "search",
            "scope",
            "graph_search",
            "match_entities",
            "_search_vector",
            "_search_hybrid",
            "_rerank_candidate_limit",
            "_rerank_hybrid_candidates",
            "_apply_rerank_results",
        ]
    )


__all__ = [
    "AgentKnowledgeBaseBinding",
    "EntityRef",
    "GraphSearchChunk",
    "GraphSearchReason",
    "GraphSearchResult",
    "RelationRef",
    "SearchMode",
    "resolve_agent_kb_ids",
    "search",
    "scope",
    "graph_search",
    "match_entities",
    "_search_vector",
    "_search_hybrid",
    "_rerank_candidate_limit",
    "_rerank_hybrid_candidates",
    "_apply_rerank_results",
]
