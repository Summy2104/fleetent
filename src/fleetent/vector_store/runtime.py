from fleetent.agent_config import AgentFile
from fleetent.model import ModelPolicySnapshot
from fleetent.vector_store.backend import (
    SearchResult,
    VectorBackend,
    create_vector_backend,
)
from fleetent.vector_store.embeddings import (
    DeterministicEmbeddingProvider,
    EmbeddingProvider,
    create_embedding_provider_from_policy,
)

_embedding: EmbeddingProvider
_backend: VectorBackend


def _platform_database_url() -> str:
    """The home-derived platform DB url; the vector backend's fallback DB path."""
    from fleetent.config import Settings

    return Settings().database_url


def _configure(agent: AgentFile) -> None:
    global _embedding, _backend

    if not agent.name:
        _embedding = DeterministicEmbeddingProvider()
    else:
        _embedding = create_embedding_provider_from_policy(ModelPolicySnapshot.from_agent(agent))
    database_url = agent.vector_store.database_url or _platform_database_url()
    _backend = create_vector_backend(agent.vector_store, database_url=database_url)


def configure_from_active_agent() -> None:
    """Configure the embedding/vector singletons from the active agent's
    embedding/vector_store blocks (a neutral default when no single agent is
    published); the DB path falls back to the home-derived platform DB url."""
    from fleetent import agent_config

    _configure(agent_config.active_agent_or_default())


configure_from_active_agent()


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


async def embed_text(text: str) -> list[float]:
    """Embed *text* using the configured embedding provider.

    Exposes the embedding step separately so callers that own their own
    VectorBackend (e.g. per-tenant shared memory) can embed via the shared
    provider while storing in a backend other than the global _backend.
    """
    return await _embedding.embed(text)


def _validate_id(id: str) -> None:
    if not id.strip():
        raise ValueError("id must not be empty")


def _validate_namespace(namespace: str) -> None:
    if not namespace.strip():
        raise ValueError("namespace must not be empty")
