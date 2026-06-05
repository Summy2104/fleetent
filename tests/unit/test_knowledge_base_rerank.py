import pytest

from fleetent.config import RerankSettings, Settings
from fleetent.intelligence.knowledge_base.models import KnowledgeChunk
from fleetent.intelligence.vector_store.rerank import (
    DeterministicRerankProvider,
    DisabledRerankProvider,
    HttpRerankProvider,
    RerankProviderError,
    RerankResult,
    create_rerank_provider,
)


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
    monkeypatch.setattr(runtime, "_settings", lambda: Settings())
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


async def test_disabled_provider_always_raises():
    provider = DisabledRerankProvider()

    with pytest.raises(RerankProviderError, match="disabled"):
        await provider.rerank("query", ["doc-a", "doc-b"])


async def test_deterministic_provider_ranks_by_lexical_overlap():
    provider = DeterministicRerankProvider()

    results = await provider.rerank("alpha beta", ["alpha beta gamma", "unrelated words"])

    assert [result.index for result in results] == [0, 1]
    assert results[0].score > results[1].score


async def test_deterministic_provider_top_n_truncates_results():
    provider = DeterministicRerankProvider()

    results = await provider.rerank("alpha", ["alpha one", "alpha two", "alpha three"], top_n=2)

    assert len(results) == 2


async def test_deterministic_provider_top_n_zero_returns_empty():
    provider = DeterministicRerankProvider()

    assert await provider.rerank("alpha", ["alpha one", "alpha two"], top_n=0) == []


async def test_deterministic_provider_handles_empty_query_and_documents():
    provider = DeterministicRerankProvider()

    results = await provider.rerank("", ["", "alpha"])

    assert len(results) == 2
    assert all(0.0 <= result.score <= 1.0 for result in results)


def test_create_rerank_provider_disabled_backend():
    provider = create_rerank_provider(RerankSettings(backend="disabled"))

    assert isinstance(provider, DisabledRerankProvider)


def test_create_rerank_provider_deterministic_backend():
    provider = create_rerank_provider(RerankSettings(backend="deterministic"))

    assert isinstance(provider, DeterministicRerankProvider)


def test_create_rerank_provider_unsupported_backend_fails_fast():
    with pytest.raises(ValueError, match="Unsupported rerank.backend"):
        create_rerank_provider(RerankSettings(backend="mystery"))


def test_http_provider_requires_non_empty_endpoint():
    with pytest.raises(ValueError, match="endpoint must not be empty"):
        HttpRerankProvider(endpoint="   ", model="bge-reranker")


async def test_http_rerank_wraps_connection_error(monkeypatch):
    import httpx

    provider = create_rerank_provider(
        RerankSettings(backend="http", endpoint="http://rerank.test/rerank", model="bge")
    )

    import respx

    with respx.mock:
        respx.post("http://rerank.test/rerank").mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(RerankProviderError, match="request failed"):
            await provider.rerank("query", ["doc-a"])


async def test_http_rerank_error_detail_from_string_error_field():
    import httpx
    import respx

    provider = create_rerank_provider(
        RerankSettings(backend="http", endpoint="http://rerank.test/rerank", model="bge")
    )

    with respx.mock:
        respx.post("http://rerank.test/rerank").mock(
            return_value=httpx.Response(500, json={"error": "boom-detail"})
        )
        with pytest.raises(RerankProviderError, match="boom-detail"):
            await provider.rerank("query", ["doc-a"])


async def test_http_rerank_error_detail_from_message_field():
    import httpx
    import respx

    provider = create_rerank_provider(
        RerankSettings(backend="http", endpoint="http://rerank.test/rerank", model="bge")
    )

    with respx.mock:
        respx.post("http://rerank.test/rerank").mock(
            return_value=httpx.Response(503, json={"message": "service-down"})
        )
        with pytest.raises(RerankProviderError, match="service-down"):
            await provider.rerank("query", ["doc-a"])


async def test_http_rerank_status_error_without_detail():
    import httpx
    import respx

    provider = create_rerank_provider(
        RerankSettings(backend="http", endpoint="http://rerank.test/rerank", model="bge")
    )

    with respx.mock:
        respx.post("http://rerank.test/rerank").mock(
            return_value=httpx.Response(500, content=b"not json body")
        )
        with pytest.raises(RerankProviderError, match="status 500"):
            await provider.rerank("query", ["doc-a"])


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"no_results": []}, "missing results"),
        ({"results": "oops"}, "missing results"),
        ({"results": ["not-a-dict"]}, "invalid result"),
        ({"results": [{"score": 0.5}]}, "index is invalid"),
    ],
)
async def test_http_rerank_extract_results_validation(body, message):
    import httpx
    import respx

    provider = create_rerank_provider(
        RerankSettings(backend="http", endpoint="http://rerank.test/rerank", model="bge")
    )

    with respx.mock:
        respx.post("http://rerank.test/rerank").mock(return_value=httpx.Response(200, json=body))
        with pytest.raises(RerankProviderError, match=message):
            await provider.rerank("query", ["doc-a"])


async def test_http_rerank_omits_authorization_when_env_unset(monkeypatch):
    import httpx
    import respx

    monkeypatch.delenv("RERANK_MISSING_KEY", raising=False)
    provider = create_rerank_provider(
        RerankSettings(
            backend="http",
            endpoint="http://rerank.test/rerank",
            model="bge",
            api_key_env="RERANK_MISSING_KEY",
        )
    )
    captured: dict[str, str] = {}

    def capture(request):
        captured.update(request.headers)
        return httpx.Response(200, json={"results": []})

    with respx.mock:
        respx.post("http://rerank.test/rerank").mock(side_effect=capture)
        await provider.rerank("query", ["doc-a"])

    assert "authorization" not in captured
