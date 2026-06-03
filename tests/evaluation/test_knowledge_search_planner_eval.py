import json
from pathlib import Path

from fleetent.intelligence.knowledge_base import KnowledgeSearchOptions, plan_knowledge_search

FIXTURE = Path("tests/evaluation/fixtures/knowledge_search_planner/basic.json")


def test_planner_evaluation_fixture_covers_ordinary_relation_and_rerank_queries():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    for case in payload["queries"]:
        plan = plan_knowledge_search(
            case["query"],
            KnowledgeSearchOptions(
                tenant_id="default",
                kb_ids=["global"],
                limit=case["limit"],
                rerank=case["rerank"],
            ),
        )

        assert [step.kind for step in plan.steps] == case["expected_steps"]
        assert [step.rerank for step in plan.steps] == case["expected_rerank"]
        assert plan.reason == case["expected_reason"]
