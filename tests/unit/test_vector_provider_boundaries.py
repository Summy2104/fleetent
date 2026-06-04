import json

import httpx
import pytest
import respx

from fleetent.config import EmbeddingSettings, RerankSettings


async def test_http_embedding_sends_dimensions_payload_and_authorization(monkeypatch):
    from fleetent.intelligence.vector_store.embeddings import create_embedding_provider

    monkeypatch.setenv("EMBEDDING_API_KEY", "secret-token")
    provider = create_embedding_provider(
        EmbeddingSettings(
            backend="http",
            dimensions=3,
            endpoint="http://embedding.test/v1/embeddings",
            model="bge-m3",
            api_key_env="EMBEDDING_API_KEY",
        )
    )
    captured: httpx.Request | None = None

    def capture(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    with respx.mock:
        respx.post("http://embedding.test/v1/embeddings").mock(side_effect=capture)

        vector = await provider.embed("hello world")

    assert vector == [0.1, 0.2, 0.3]
    assert captured is not None
    assert captured.headers["authorization"] == "Bearer secret-token"
    assert json.loads(captured.content) == {
        "model": "bge-m3",
        "input": ["hello world"],
        "dimensions": 3,
    }


async def test_http_embedding_resolves_endpoint_model_and_dimensions_from_env(monkeypatch):
    from fleetent.intelligence.vector_store.embeddings import create_embedding_provider

    monkeypatch.setenv("EMBEDDING_ENDPOINT", "http://embedding.test/v1/embeddings")
    monkeypatch.setenv("EMBEDDING_MODEL", "bge-m3")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "3")
    provider = create_embedding_provider(
        EmbeddingSettings(
            backend="http",
            endpoint_env="EMBEDDING_ENDPOINT",
            model_env="EMBEDDING_MODEL",
            dimensions_env="EMBEDDING_DIMENSIONS",
        )
    )

    with respx.mock:
        respx.post("http://embedding.test/v1/embeddings").mock(
            return_value=httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})
        )

        vector = await provider.embed("hello world")

    assert vector == [0.1, 0.2, 0.3]


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]}), "expected 3"),
        (httpx.Response(200, json={"data": [{"embedding": [0.1, "bad", 0.3]}]}), "non-numeric"),
        (httpx.Response(200, json={"data": []}), "missing embedding"),
        (httpx.Response(200, content=b"{not json"), "malformed JSON"),
    ],
)
async def test_http_embedding_rejects_malformed_or_wrong_dimension_response(response, message):
    from fleetent.intelligence.vector_store.embeddings import (
        EmbeddingProviderError,
        create_embedding_provider,
    )

    provider = create_embedding_provider(
        EmbeddingSettings(
            backend="http",
            dimensions=3,
            endpoint="http://embedding.test/v1/embeddings",
            model="bge-m3",
        )
    )

    with respx.mock:
        respx.post("http://embedding.test/v1/embeddings").mock(return_value=response)

        with pytest.raises(EmbeddingProviderError, match=message):
            await provider.embed("hello")


async def test_http_embedding_failure_does_not_fallback_to_deterministic():
    from fleetent.intelligence.vector_store.embeddings import (
        EmbeddingProviderError,
        create_embedding_provider,
    )

    provider = create_embedding_provider(
        EmbeddingSettings(
            backend="http",
            dimensions=3,
            endpoint="http://embedding.test/v1/embeddings",
            model="bge-m3",
        )
    )

    with respx.mock:
        respx.post("http://embedding.test/v1/embeddings").mock(return_value=httpx.Response(503))

        with pytest.raises(EmbeddingProviderError, match="status 503"):
            await provider.embed("python debugging")


async def test_http_rerank_sends_payload_and_authorization(monkeypatch):
    from fleetent.intelligence.vector_store.rerank import create_rerank_provider

    monkeypatch.setenv("RERANK_API_KEY", "secret-token")
    provider = create_rerank_provider(
        RerankSettings(
            backend="http",
            endpoint="http://rerank.test/rerank",
            model="bge-reranker",
            api_key_env="RERANK_API_KEY",
        )
    )
    captured: httpx.Request | None = None

    def capture(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(200, json={"results": [{"index": 1, "score": 0.9}]})

    with respx.mock:
        respx.post("http://rerank.test/rerank").mock(side_effect=capture)

        results = await provider.rerank("query", ["doc-a", "doc-b"], top_n=1)

    assert [(result.index, result.score) for result in results] == [(1, 0.9)]
    assert captured is not None
    assert captured.headers["authorization"] == "Bearer secret-token"
    assert json.loads(captured.content) == {
        "model": "bge-reranker",
        "query": "query",
        "documents": ["doc-a", "doc-b"],
        "top_n": 1,
    }


async def test_http_rerank_resolves_endpoint_and_model_from_env(monkeypatch):
    from fleetent.intelligence.vector_store.rerank import create_rerank_provider

    monkeypatch.setenv("RERANK_ENDPOINT", "http://rerank.test/rerank")
    monkeypatch.setenv("RERANK_MODEL", "bge-reranker")
    provider = create_rerank_provider(
        RerankSettings(
            backend="http",
            endpoint_env="RERANK_ENDPOINT",
            model_env="RERANK_MODEL",
        )
    )

    with respx.mock:
        respx.post("http://rerank.test/rerank").mock(
            return_value=httpx.Response(200, json={"results": [{"index": 0, "score": 0.9}]})
        )

        results = await provider.rerank("query", ["doc-a"])

    assert [(result.index, result.score) for result in results] == [(0, 0.9)]


async def test_http_rerank_preserves_provider_rank_and_score_order():
    from fleetent.intelligence.vector_store.rerank import create_rerank_provider

    provider = create_rerank_provider(
        RerankSettings(
            backend="http",
            endpoint="http://rerank.test/rerank",
            model="bge-reranker",
        )
    )

    with respx.mock:
        respx.post("http://rerank.test/rerank").mock(
            return_value=httpx.Response(
                200,
                json={"results": [{"index": 2, "score": 0.7}, {"index": 0, "score": 0.6}]},
            )
        )

        results = await provider.rerank("query", ["doc-a", "doc-b", "doc-c"])

    assert [(result.index, result.score) for result in results] == [(2, 0.7), (0, 0.6)]


async def test_http_rerank_accepts_relevance_score_field():
    from fleetent.intelligence.vector_store.rerank import create_rerank_provider

    provider = create_rerank_provider(
        RerankSettings(
            backend="http",
            endpoint="http://rerank.test/rerank",
            model="jina-reranker",
        )
    )

    with respx.mock:
        respx.post("http://rerank.test/rerank").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"index": 1, "relevance_score": 0.92},
                        {"index": 0, "relevance_score": 0.71},
                    ]
                },
            )
        )

        results = await provider.rerank("query", ["doc-a", "doc-b"])

    assert [(result.index, result.score) for result in results] == [(1, 0.92), (0, 0.71)]


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(429, json={"error": {"message": "rate limited"}}), "rate limited"),
        (httpx.Response(200, content=b"{not json"), "malformed JSON"),
        (httpx.Response(200, json={"results": [{"index": 3, "score": 0.9}]}), "out of range"),
        (httpx.Response(200, json={"results": [{"index": 0, "score": "high"}]}), "score"),
    ],
)
async def test_http_rerank_rejects_timeout_malformed_and_provider_error(response, message):
    from fleetent.intelligence.vector_store.rerank import (
        RerankProviderError,
        create_rerank_provider,
    )

    provider = create_rerank_provider(
        RerankSettings(
            backend="http",
            endpoint="http://rerank.test/rerank",
            model="bge-reranker",
        )
    )

    with respx.mock:
        respx.post("http://rerank.test/rerank").mock(return_value=response)

        with pytest.raises(RerankProviderError, match=message):
            await provider.rerank("query", ["doc-a"])


async def test_http_rerank_timeout_does_not_fallback_to_deterministic():
    from fleetent.intelligence.vector_store.rerank import (
        RerankProviderError,
        create_rerank_provider,
    )

    provider = create_rerank_provider(
        RerankSettings(
            backend="http",
            endpoint="http://rerank.test/rerank",
            model="bge-reranker",
        )
    )

    with respx.mock:
        respx.post("http://rerank.test/rerank").mock(side_effect=httpx.TimeoutException("slow"))

        with pytest.raises(RerankProviderError, match="timed out"):
            await provider.rerank("query", ["doc-a"])
