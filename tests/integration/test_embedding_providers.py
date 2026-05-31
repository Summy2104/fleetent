import json

import httpx
import pytest
import respx

from fleetent.config import EmbeddingSettings


async def test_default_embedding_provider_is_deterministic_and_stable():
    from fleetent.intelligence.vector_store.embeddings import (
        DeterministicEmbeddingProvider,
        create_embedding_provider,
    )

    provider = create_embedding_provider(EmbeddingSettings())

    assert isinstance(provider, DeterministicEmbeddingProvider)
    assert await provider.embed("Python debugging") == await provider.embed("Python debugging")


def test_http_embedding_provider_can_be_configured():
    from fleetent.intelligence.vector_store.embeddings import (
        HttpEmbeddingProvider,
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

    assert isinstance(provider, HttpEmbeddingProvider)


async def test_http_embedding_sends_openai_payload_and_authorization(monkeypatch):
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
    assert json.loads(captured.content) == {"model": "bge-m3", "input": ["hello world"]}


async def test_http_embedding_empty_text_returns_zero_vector_without_request():
    from fleetent.intelligence.vector_store.embeddings import create_embedding_provider

    provider = create_embedding_provider(
        EmbeddingSettings(
            backend="http",
            dimensions=3,
            endpoint="http://embedding.test/v1/embeddings",
            model="bge-m3",
        )
    )

    with respx.mock(assert_all_called=False):
        route = respx.post("http://embedding.test/v1/embeddings").mock(
            return_value=httpx.Response(200, json={"data": [{"embedding": [1.0, 2.0, 3.0]}]})
        )

        assert await provider.embed("   ") == [0.0, 0.0, 0.0]

    assert not route.called


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(500, json={"error": "boom"}), "status 500"),
        (httpx.Response(200, content=b"{not json"), "malformed JSON"),
        (httpx.Response(200, json={"data": [{}]}), "missing embedding"),
        (httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]}), "dimension"),
    ],
)
async def test_http_embedding_errors_are_explicit(response, message):
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


async def test_http_embedding_timeout_is_explicit():
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
        respx.post("http://embedding.test/v1/embeddings").mock(
            side_effect=httpx.TimeoutException("slow")
        )

        with pytest.raises(EmbeddingProviderError, match="timed out"):
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
