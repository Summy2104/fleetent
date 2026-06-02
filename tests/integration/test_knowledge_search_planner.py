from fleetent.intelligence.knowledge_base.graph_search import GraphSearchChunk, GraphSearchResult
from fleetent.intelligence.knowledge_base.models import KnowledgeChunk
from fleetent.intelligence.knowledge_base.planner import (
    KnowledgeSearchOptions,
    KnowledgeSearchPlan,
    KnowledgeSearchStep,
    execute_knowledge_search_plan,
    plan_knowledge_search,
)


def _chunk(chunk_id: str, score: float = 0.5) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=chunk_id,
        document_id=f"doc-{chunk_id}",
        tenant_id="tenant-a",
        kb_id="global",
        filename=f"{chunk_id}.md",
        content=f"content {chunk_id}",
        position=0,
        score=score,
        source="manual",
        source_url=None,
    )


async def test_execute_default_hybrid_plan_passes_scope_and_limit(monkeypatch):
    from fleetent.intelligence.knowledge_base import planner

    calls: list[dict[str, object]] = []

    async def hybrid_search(
        query: str,
        tenant_id: str | None = None,
        kb_ids: list[str] | None = None,
        limit: int = 10,
        mode: str = "vector",
        rerank: bool = False,
    ) -> list[KnowledgeChunk]:
        calls.append(
            {
                "query": query,
                "tenant_id": tenant_id,
                "kb_ids": kb_ids,
                "limit": limit,
                "mode": mode,
                "rerank": rerank,
            }
        )
        return [_chunk("hybrid-a")]

    monkeypatch.setattr(planner, "search", hybrid_search)

    plan = plan_knowledge_search(
        "restart cache",
        KnowledgeSearchOptions(tenant_id="tenant-a", kb_ids=["global"], limit=3),
    )
    results = await execute_knowledge_search_plan(plan)

    assert [chunk.id for chunk in results] == ["hybrid-a"]
    assert calls == [
        {
            "query": "restart cache",
            "tenant_id": "tenant-a",
            "kb_ids": ["global"],
            "limit": 3,
            "mode": "hybrid",
            "rerank": False,
        }
    ]


async def test_execute_graph_plan_fills_dedupes_and_respects_limit(monkeypatch):
    from fleetent.intelligence.knowledge_base import planner

    calls: list[tuple[str, int, bool]] = []
    graph_chunk = _chunk("graph-a", score=1.0)
    duplicate = _chunk("graph-a", score=0.8)
    fill_chunk = _chunk("hybrid-b", score=0.7)

    async def graph_first(
        query: str,
        tenant_id: str | None = None,
        kb_ids: list[str] | None = None,
        limit: int = 10,
        depth: int = 1,
    ) -> GraphSearchResult:
        calls.append(("graph", limit, False))
        return GraphSearchResult(
            query=query,
            tenant_id=tenant_id or "default",
            kb_ids=kb_ids or ["global"],
            depth=depth,
            chunks=[
                GraphSearchChunk(
                    chunk=graph_chunk,
                    graph_score=1.0,
                    reason="direct_entity_match",
                )
            ],
        )

    async def hybrid_fill(
        query: str,
        tenant_id: str | None = None,
        kb_ids: list[str] | None = None,
        limit: int = 10,
        mode: str = "vector",
        rerank: bool = False,
    ) -> list[KnowledgeChunk]:
        calls.append(("hybrid", limit, rerank))
        return [duplicate, fill_chunk]

    monkeypatch.setattr(planner, "graph_search", graph_first)
    monkeypatch.setattr(planner, "search", hybrid_fill)

    plan = KnowledgeSearchPlan(
        query="Which service depends on Billing API?",
        tenant_id="tenant-a",
        kb_ids=["global"],
        limit=2,
        steps=[
            KnowledgeSearchStep("graph_search", "relation_like_query"),
            KnowledgeSearchStep("hybrid_fill", "relation_like_query", rerank=True),
        ],
        reason="relation_like_query",
    )
    results = await execute_knowledge_search_plan(plan)

    assert [chunk.id for chunk in results] == ["graph-a", "hybrid-b"]
    assert calls == [("graph", 2, False), ("hybrid", 1, True)]
