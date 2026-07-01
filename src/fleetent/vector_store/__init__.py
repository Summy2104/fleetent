from fleetent.vector_store.backend import SearchResult
from fleetent.vector_store.namespaces import (
    agent_memory_namespace,
    knowledge_namespace,
    memory_namespace,
)
from fleetent.vector_store.reindex import (
    IndexableItem,
    ReindexRequest,
    ReindexSummary,
    reindex,
)
from fleetent.vector_store.rerank import (
    RerankProvider,
    RerankProviderError,
    RerankResult,
    create_rerank_provider,
)
from fleetent.vector_store.runtime import (
    EmbeddingIdentity,
    clear_namespace,
    configure_from_active_agent,
    current_embedding_identity,
    delete,
    embed_text,
    search,
    upsert,
)

__all__ = [
    "IndexableItem",
    "ReindexRequest",
    "ReindexSummary",
    "RerankProvider",
    "RerankProviderError",
    "RerankResult",
    "SearchResult",
    "EmbeddingIdentity",
    "clear_namespace",
    "configure_from_active_agent",
    "current_embedding_identity",
    "create_rerank_provider",
    "delete",
    "embed_text",
    "agent_memory_namespace",
    "knowledge_namespace",
    "memory_namespace",
    "reindex",
    "search",
    "upsert",
]
