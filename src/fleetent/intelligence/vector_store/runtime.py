from fleetent.config import Settings
from fleetent.intelligence.vector_store.backend import SearchResult, create_vector_backend
from fleetent.intelligence.vector_store.embeddings import (
    EmbeddingProvider,
    create_embedding_provider,
)

_embedding: EmbeddingProvider
_backend = create_vector_backend(Settings(anthropic_api_key="").vector_store)


def _configure(settings: Settings) -> None:
    global _embedding, _backend

    _embedding = create_embedding_provider(settings.embedding)
    _backend = create_vector_backend(settings.vector_store)


_configure(Settings(anthropic_api_key=""))


async def upsert(id: str, text: str, namespace: str) -> None:
    """Embed text and upsert vector by id in namespace."""
    _validate_id(id)
    _validate_namespace(namespace)
    await _backend.upsert(id, await _embedding.embed(text), namespace)


async def search(query: str, namespace: str, limit: int = 10) -> list[SearchResult]:
    """Return top-k ids by similarity within namespace."""
    _validate_namespace(namespace)
    return await _backend.search(await _embedding.embed(query), namespace, limit)


async def delete(id: str, namespace: str) -> None:
    """Delete one vector by id from namespace."""
    _validate_id(id)
    _validate_namespace(namespace)
    await _backend.delete(id, namespace)


def _validate_id(id: str) -> None:
    if not id.strip():
        raise ValueError("id must not be empty")


def _validate_namespace(namespace: str) -> None:
    if not namespace.strip():
        raise ValueError("namespace must not be empty")
