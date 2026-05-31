import json
from dataclasses import fields

import httpx
import pytest
import respx

from fleetent.config import RerankSettings


def test_rerank_result_shape_is_public():
    from fleetent.intelligence.vector_store.rerank import RerankResult

    assert [field.name for field in fields(RerankResult)] == ["index", "score"]
    assert RerankResult(index=1, score=0.5).index == 1


async def test_disabled_rerank_provider_fails_explicitly():
    from fleetent.intelligence.vector_store.rerank import (
        RerankProviderError,
        create_rerank_provider,
    )

    provider = create_rerank_provider(RerankSettings())

    with pytest.raises(RerankProviderError, match="disabled"):
        await provider.rerank("query", ["document"])


async def test_deterministic_rerank_provider_returns_stable_order():
    from fleetent.intelligence.vector_store.rerank import create_rerank_provider

    provider = create_rerank_provider(RerankSettings(backend="deterministic"))

    first = await provider.rerank("python debugging", ["debug python", "unrelated"], top_n=2)
    second = await provider.rerank("python debugging", ["debug python", "unrelated"], top_n=2)

    assert first == second
    assert [result.index for result in first] == [0, 1]
    assert first[0].score >= first[1].score


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


async def test_http_rerank_parses_provider_result_order():
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


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(500, json={"error": "boom"}), "status 500"),
        (httpx.Response(200, content=b"{not json"), "malformed JSON"),
        (httpx.Response(200, json={"results": [{"index": 3, "score": 0.9}]}), "out of range"),
        (httpx.Response(200, json={"results": [{"index": 0, "score": "high"}]}), "score"),
    ],
)
async def test_http_rerank_errors_are_explicit(response, message):
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


async def test_http_rerank_timeout_is_explicit():
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


async def test_http_rerank_failure_does_not_fallback_to_deterministic():
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
        respx.post("http://rerank.test/rerank").mock(return_value=httpx.Response(503))

        with pytest.raises(RerankProviderError, match="status 503"):
            await provider.rerank("python debugging", ["debug python"])
