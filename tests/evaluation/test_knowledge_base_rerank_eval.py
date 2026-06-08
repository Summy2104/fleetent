import json
from pathlib import Path

from fleetent import agent_config
from fleetent.agent_config import AgentFile, default_models
from fleetent.config import KnowledgeBaseSettings, RerankSettings
from fleetent.db import create_database
from tests.integration.test_migrations import apply_migrations

FIXTURE = Path("tests/evaluation/fixtures/knowledge_base_rerank/basic.json")


async def test_deterministic_rerank_promotes_expected_chunk(monkeypatch, tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    database = _patch_runtime(monkeypatch, tmp_path)

    from fleetent.knowledge_base import runtime
    from fleetent.vector_store import SearchResult

    documents: dict[str, str] = {}
    for item in payload["documents"]:
        document = await runtime.ingest_text(
            filename=f"{item['id']}.md",
            content=item["content"],
            tenant_id="default",
            kb_id="global",
            source="evaluation",
        )
        documents[item["id"]] = document.id

    original_store_cls = runtime.KnowledgeStore

    class EvaluationStore(original_store_cls):
        def search_keyword(
            self,
            query: str,
            tenant_id: str,
            kb_ids: list[str],
            limit: int,
        ):
            return []

    async def vector_search(query: str, namespace: str, limit: int):
        return [
            SearchResult(id=f"{documents[item]}:chunk:0", score=1.0 - index * 0.1)
            for index, item in enumerate(payload["vector_order"])
        ][:limit]

    monkeypatch.setattr(runtime, "KnowledgeStore", EvaluationStore)
    monkeypatch.setattr(runtime.vector_store, "search", vector_search)

    case = payload["queries"][0]
    baseline = await runtime.search(
        case["text"],
        tenant_id="default",
        kb_ids=["global"],
        limit=case["top_k"],
        mode="hybrid",
    )
    reranked = await runtime.search(
        case["text"],
        tenant_id="default",
        kb_ids=["global"],
        limit=case["top_k"],
        mode="hybrid",
        rerank=True,
    )

    assert baseline[0].document_id == documents[case["forbidden_top_document"]]
    assert reranked[0].document_id == documents[case["expected_top_document"]]
    assert reranked[0].document_id != documents[case["forbidden_top_document"]]
    assert database is not None


def test_real_rerank_evaluation_is_opt_in(monkeypatch):
    monkeypatch.delenv("FLEETENT_EVAL_REAL_RERANK", raising=False)

    assert not _real_rerank_enabled()


def _patch_runtime(monkeypatch, tmp_path):
    from fleetent.knowledge_base import runtime

    db_path = tmp_path / "knowledge.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    agent = AgentFile(
        name="rerank-eval",
        version=1,
        models=default_models(),
        rerank=RerankSettings(backend="deterministic"),
    )
    kb_settings = KnowledgeBaseSettings(chunk_size=500, chunk_overlap=0)
    monkeypatch.setattr(runtime, "_database", lambda: database)
    monkeypatch.setattr(agent_config, "active_agent_or_default", lambda: agent)
    monkeypatch.setattr(runtime, "_kb_config", lambda: kb_settings)
    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    monkeypatch.setattr(runtime.vector_store, "delete", _noop_delete)
    return database


def _real_rerank_enabled() -> bool:
    import os

    return os.getenv("FLEETENT_EVAL_REAL_RERANK", "").lower() in {"1", "true", "yes"}


async def _noop_upsert(chunk_id: str, content: str, namespace: str) -> None:
    return None


async def _noop_delete(chunk_id: str, namespace: str) -> None:
    return None
