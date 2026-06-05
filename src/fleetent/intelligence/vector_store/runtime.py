from fleetent.config import Settings
from fleetent.intelligence.vector_store.backend import (
    SearchResult,
    VectorBackend,
    create_vector_backend,
)
from fleetent.intelligence.vector_store.embeddings import (
    EmbeddingProvider,
    create_embedding_provider,
)

_embedding: EmbeddingProvider
_backend: VectorBackend


def _configure(settings: Settings) -> None:
    global _embedding, _backend

    _embedding = create_embedding_provider(settings.embedding)
    _backend = _create_vector_backend(settings)


def _create_vector_backend(settings: Settings) -> VectorBackend:
    database_url = settings.vector_store.database_url or settings.database_url
    return create_vector_backend(settings.vector_store, database_url=database_url)


def configure_from_active_agent() -> None:
    """Reconfigure the embedding/vector singletons from the standalone process's active
    agent (its embedding/vector_store blocks); the DB path still falls back to the
    home-derived Settings.database_url. No-op when no single agent is published."""
    from fleetent import agent_config

    agent = agent_config.active_agent()
    if agent is None:
        return
    global _embedding, _backend
    _embedding = create_embedding_provider(agent.embedding)
    database_url = agent.vector_store.database_url or Settings(anthropic_api_key="").database_url
    _backend = create_vector_backend(agent.vector_store, database_url=database_url)


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


async def clear_namespace(namespace: str) -> None:
    """Delete all vectors in namespace."""
    _validate_namespace(namespace)
    await _backend.clear_namespace(namespace)


def _validate_id(id: str) -> None:
    if not id.strip():
        raise ValueError("id must not be empty")


def _validate_namespace(namespace: str) -> None:
    if not namespace.strip():
        raise ValueError("namespace must not be empty")
