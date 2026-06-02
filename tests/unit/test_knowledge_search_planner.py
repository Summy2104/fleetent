def test_planner_public_api_is_importable():
    from fleetent.intelligence.knowledge_base import (
        KnowledgeSearchOptions,
        KnowledgeSearchPlan,
        KnowledgeSearchStep,
        execute_knowledge_search_plan,
        plan_knowledge_search,
    )

    assert KnowledgeSearchOptions is not None
    assert KnowledgeSearchPlan is not None
    assert KnowledgeSearchStep is not None
    assert plan_knowledge_search is not None
    assert execute_knowledge_search_plan is not None


def test_default_query_uses_hybrid_search_with_reason():
    from fleetent.intelligence.knowledge_base import KnowledgeSearchOptions, plan_knowledge_search

    plan = plan_knowledge_search(
        "How do I restart the cache service?",
        KnowledgeSearchOptions(tenant_id="tenant-a", kb_ids=["runbook"], limit=3),
    )

    assert plan.query == "How do I restart the cache service?"
    assert plan.tenant_id == "tenant-a"
    assert plan.kb_ids == ["runbook"]
    assert plan.limit == 3
    assert [(step.kind, step.reason, step.rerank) for step in plan.steps] == [
        ("hybrid_search", "default_hybrid", False)
    ]
    assert plan.reason == "default_hybrid"


def test_entity_or_relation_query_uses_graph_first_with_hybrid_fill():
    from fleetent.intelligence.knowledge_base import KnowledgeSearchOptions, plan_knowledge_search

    plan = plan_knowledge_search(
        "Which service depends on Billing API?",
        KnowledgeSearchOptions(tenant_id="tenant-a", kb_ids=["runbook"], limit=5),
    )

    assert [(step.kind, step.reason) for step in plan.steps] == [
        ("graph_search", "relation_like_query"),
        ("hybrid_fill", "relation_like_query"),
    ]
    assert plan.reason == "relation_like_query"


def test_rerank_option_marks_hybrid_steps_only():
    from fleetent.intelligence.knowledge_base import KnowledgeSearchOptions, plan_knowledge_search

    default_plan = plan_knowledge_search(
        "Cache restart",
        KnowledgeSearchOptions(tenant_id="tenant-a", kb_ids=["runbook"], rerank=True),
    )
    relation_plan = plan_knowledge_search(
        "Which service depends on Billing API?",
        KnowledgeSearchOptions(tenant_id="tenant-a", kb_ids=["runbook"], rerank=True),
    )

    assert [(step.kind, step.rerank) for step in default_plan.steps] == [("hybrid_search", True)]
    assert [(step.kind, step.rerank) for step in relation_plan.steps] == [
        ("graph_search", False),
        ("hybrid_fill", True),
    ]


async def test_executor_records_retrieval_summary_log(monkeypatch):
    from fleetent.intelligence.knowledge_base import planner
    from fleetent.intelligence.knowledge_base.models import KnowledgeChunk

    events: list[tuple[str, dict[str, object]]] = []

    class FakeLogger:
        def info(self, message: str, **fields: object) -> None:
            events.append((message, fields))

    async def hybrid_search(
        query: str,
        tenant_id: str | None = None,
        kb_ids: list[str] | None = None,
        limit: int = 10,
        mode: str = "vector",
        rerank: bool = False,
    ) -> list[KnowledgeChunk]:
        return [
            KnowledgeChunk(
                id="chunk-a",
                document_id="doc-a",
                tenant_id=tenant_id or "default",
                kb_id=(kb_ids or ["global"])[0],
                filename="a.md",
                content="content",
                position=0,
                score=0.5,
                source="manual",
                source_url=None,
            )
        ]

    monkeypatch.setattr(planner, "_logger", FakeLogger())
    monkeypatch.setattr(planner, "search", hybrid_search)

    plan = planner.plan_knowledge_search(
        "restart cache",
        planner.KnowledgeSearchOptions(tenant_id="tenant-a", kb_ids=["global"], rerank=True),
    )
    await planner.execute_knowledge_search_plan(plan)

    assert events == [
        (
            "kb_search_plan_executed",
            {
                "tenant_id": "tenant-a",
                "kb_ids": ["global"],
                "limit": 10,
                "steps": ["hybrid_search"],
                "reasons": ["default_hybrid"],
                "graph_result_count": 0,
                "hybrid_fill_count": 0,
                "rerank_requested": True,
            },
        )
    ]
