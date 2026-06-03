import pytest

from fleetent.config import RerankSettings, Settings
from fleetent.intelligence.knowledge_base.models import KnowledgeChunk
from fleetent.intelligence.vector_store.rerank import RerankProviderError, RerankResult


def _chunk(chunk_id: str, position: int, score: float) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=chunk_id,
        document_id=f"doc-{chunk_id}",
        tenant_id="tenant-a",
        kb_id="global",
        filename=f"{chunk_id}.md",
        content=f"content {chunk_id}",
        position=position,
        score=score,
        source="manual",
        source_url=None,
    )


def test_rerank_candidate_limit_uses_stable_runtime_constants():
    from fleetent.intelligence.knowledge_base import runtime

    assert runtime._rerank_candidate_limit(1) == 20
    assert runtime._rerank_candidate_limit(10) == 50
    assert runtime._rerank_candidate_limit(30) == 100
    assert runtime.RERANK_CANDIDATE_MULTIPLIER == 5
    assert runtime.RERANK_CANDIDATE_MIN == 20
    assert runtime.RERANK_CANDIDATE_MAX == 100


def test_apply_rerank_results_maps_valid_indexes_and_appends_missing_candidates():
    from fleetent.intelligence.knowledge_base import runtime

    candidates = [
        _chunk("chunk-a", 0, 0.30),
        _chunk("chunk-b", 1, 0.20),
        _chunk("chunk-c", 2, 0.10),
    ]
    results = [
        RerankResult(index=1, score=0.99),
        RerankResult(index=99, score=0.88),
        RerankResult(index=-1, score=0.77),
        RerankResult(index=1, score=0.66),
    ]

    reranked = runtime._apply_rerank_results(candidates, results, limit=3)

    assert [chunk.id for chunk in reranked] == ["chunk-b", "chunk-a", "chunk-c"]
    assert [chunk.score for chunk in reranked] == [0.99, 0.30, 0.10]


async def test_search_rejects_rerank_for_vector_and_keyword_modes(monkeypatch):
    from fleetent.intelligence.knowledge_base import runtime

    called = False

    def provider_factory(settings: RerankSettings):
        nonlocal called
        called = True
        raise AssertionError("rerank provider should not be created")

    monkeypatch.setattr(runtime.rerank_runtime, "create_rerank_provider", provider_factory)

    with pytest.raises(ValueError, match="rerank only supports hybrid"):
        await runtime.search("query", mode="vector", rerank=True)

    with pytest.raises(ValueError, match="rerank only supports hybrid"):
        await runtime.search("query", mode="keyword", rerank=True)

    assert called is False


async def test_non_positive_limit_short_circuits_before_rerank_provider(monkeypatch):
    from fleetent.intelligence.knowledge_base import runtime

    called = False

    def provider_factory(settings: RerankSettings):
        nonlocal called
        called = True
        raise AssertionError("rerank provider should not be created")

    monkeypatch.setattr(runtime.rerank_runtime, "create_rerank_provider", provider_factory)

    assert await runtime.search("query", mode="hybrid", rerank=True, limit=0) == []
    assert called is False


async def test_rerank_provider_failure_falls_back_to_hybrid_order(monkeypatch):
    from fleetent.intelligence.knowledge_base import runtime

    candidates = [_chunk("chunk-a", 0, 0.30), _chunk("chunk-b", 1, 0.20)]
    events: list[tuple[str, dict[str, object]]] = []

    class FailingProvider:
        async def rerank(
            self, query: str, documents: list[str], top_n: int | None = None
        ) -> list[RerankResult]:
            raise RerankProviderError("offline")

    class FakeLogger:
        def warn(self, message: str, **fields: object) -> None:
            events.append((message, fields))

    monkeypatch.setattr(
        runtime.rerank_runtime,
        "create_rerank_provider",
        lambda settings: FailingProvider(),
    )
    monkeypatch.setattr(runtime, "_settings", lambda: Settings(anthropic_api_key="test-key"))
    monkeypatch.setattr(runtime, "_logger", FakeLogger())

    reranked = await runtime._rerank_hybrid_candidates(
        "query",
        candidates,
        tenant_id="tenant-a",
        kb_ids=["global"],
        limit=2,
    )

    assert [chunk.id for chunk in reranked] == ["chunk-a", "chunk-b"]
    assert events == [
        (
            "kb_rerank_failed",
            {
                "tenant_id": "tenant-a",
                "kb_ids": ["global"],
                "limit": 2,
                "candidate_count": 2,
                "reason": "offline",
            },
        )
    ]
