from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from fleetent.knowledge_base.models import KnowledgeChunk
from fleetent.knowledge_base.runtime import search
from fleetent.structured_logging import get_logger

KnowledgeSearchStepKind = Literal["hybrid_search", "graph_search", "hybrid_fill"]

if TYPE_CHECKING:
    from fleetent.knowledge_base.retrieval.graph_search import GraphSearchResult

_RELATION_MARKERS = (
    " depends on ",
    " dependent on ",
    " dependency",
    " relation",
    " relationship",
    " connects to ",
    " connected to ",
    " uses ",
    " upstream",
    " downstream",
    "依赖",
    "属于",
    "拥有",
    "定义",
    "冲突",
    "关联",
    "连接",
    "上游",
    "下游",
)
_ENTITY_HINTS = (
    "service",
    "system",
    "api",
    "database",
    "warehouse",
    "服务",
    "系统",
    "客户",
    "项目",
    "数据库",
)
_logger = get_logger("knowledge_base")


@dataclass(frozen=True)
class KnowledgeSearchOptions:
    tenant_id: str = "default"
    kb_ids: list[str] | None = None
    limit: int = 10
    rerank: bool = False


@dataclass(frozen=True)
class KnowledgeSearchStep:
    kind: KnowledgeSearchStepKind
    reason: str
    rerank: bool = False


@dataclass(frozen=True)
class KnowledgeSearchPlan:
    query: str
    tenant_id: str
    kb_ids: list[str]
    limit: int
    steps: list[KnowledgeSearchStep]
    reason: str


def plan_knowledge_search(
    query: str,
    options: KnowledgeSearchOptions | None = None,
) -> KnowledgeSearchPlan:
    """Create a deterministic KB retrieval plan without LLM calls."""

    resolved_options = options or KnowledgeSearchOptions()
    kb_ids = resolved_options.kb_ids or ["global"]
    reason = _plan_reason(query)
    if reason in {"relation_like_query", "entity_like_query"}:
        steps = [
            KnowledgeSearchStep("graph_search", reason, rerank=False),
            KnowledgeSearchStep("hybrid_fill", reason, rerank=resolved_options.rerank),
        ]
    else:
        steps = [
            KnowledgeSearchStep(
                "hybrid_search",
                "default_hybrid",
                rerank=resolved_options.rerank,
            )
        ]

    return KnowledgeSearchPlan(
        query=query,
        tenant_id=resolved_options.tenant_id,
        kb_ids=kb_ids,
        limit=resolved_options.limit,
        steps=steps,
        reason=steps[0].reason,
    )


async def execute_knowledge_search_plan(plan: KnowledgeSearchPlan) -> list[KnowledgeChunk]:
    """Execute a deterministic KB retrieval plan."""

    chunks: list[KnowledgeChunk] = []
    graph_count = 0
    hybrid_fill_count = 0
    seen_ids: set[str] = set()
    for step in plan.steps:
        remaining = plan.limit - len(chunks)
        if remaining <= 0:
            break
        if step.kind == "graph_search":
            graph_result = await graph_search(
                plan.query,
                tenant_id=plan.tenant_id,
                kb_ids=plan.kb_ids,
                limit=remaining,
                depth=1,
            )
            graph_chunks = [item.chunk for item in graph_result.chunks]
            graph_count += len(graph_chunks)
            _append_deduped(chunks, seen_ids, graph_chunks, plan.limit)
        elif step.kind in {"hybrid_search", "hybrid_fill"}:
            hybrid_chunks = await search(
                plan.query,
                tenant_id=plan.tenant_id,
                kb_ids=plan.kb_ids,
                limit=remaining,
                mode="hybrid",
                rerank=step.rerank,
            )
            before = len(chunks)
            _append_deduped(chunks, seen_ids, hybrid_chunks, plan.limit)
            if step.kind == "hybrid_fill":
                hybrid_fill_count += len(chunks) - before

    _logger.info(
        "kb_search_plan_executed",
        tenant_id=plan.tenant_id,
        kb_ids=plan.kb_ids,
        limit=plan.limit,
        steps=[step.kind for step in plan.steps],
        reasons=[step.reason for step in plan.steps],
        graph_result_count=graph_count,
        hybrid_fill_count=hybrid_fill_count,
        rerank_requested=any(step.rerank for step in plan.steps),
    )
    return chunks


async def graph_search(
    query: str,
    tenant_id: str | None = None,
    kb_ids: list[str] | None = None,
    limit: int = 10,
    depth: int = 1,
) -> GraphSearchResult:
    """Compatibility wrapper for legacy planner monkeypatches/tests."""

    from fleetent.knowledge_base.retrieval.graph_search import (
        graph_search as retrieval_graph_search,
    )

    return await retrieval_graph_search(
        query,
        tenant_id=tenant_id,
        kb_ids=kb_ids,
        limit=limit,
        depth=depth,
    )


def _append_deduped(
    target: list[KnowledgeChunk],
    seen_ids: set[str],
    candidates: list[KnowledgeChunk],
    limit: int,
) -> None:
    for chunk in candidates:
        if chunk.id in seen_ids:
            continue
        target.append(chunk)
        seen_ids.add(chunk.id)
        if len(target) >= limit:
            break


def _plan_reason(query: str) -> str:
    normalized = f" {query.casefold()} "
    if any(marker in normalized for marker in _RELATION_MARKERS):
        return "relation_like_query"
    if any(hint in normalized for hint in _ENTITY_HINTS) and _has_entity_like_token(query):
        return "entity_like_query"
    return "default_hybrid"


def _has_entity_like_token(query: str) -> bool:
    tokens = [token.strip(".,:;!?()[]{}") for token in query.split()]
    if any(token.isupper() and len(token) > 1 for token in tokens):
        return True
    title_tokens = [
        token
        for index, token in enumerate(tokens)
        if index > 0 and token[:1].isupper() and any(char.islower() for char in token)
    ]
    return len(title_tokens) >= 2
