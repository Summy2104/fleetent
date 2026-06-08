"""Compatibility runtime API for legacy `intelligence.knowledge_base.runtime` imports."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fleetent import vector_store
from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.knowledge_base.core import KnowledgeChunk, KnowledgeDocument, KnowledgeStore
from fleetent.knowledge_base.ingest.runtime import (
    archive as _archive_document,
)
from fleetent.knowledge_base.ingest.runtime import (
    delete as _delete_document,
)
from fleetent.knowledge_base.ingest.runtime import (
    delete_document as _delete_scoped_document,
)
from fleetent.knowledge_base.ingest.runtime import (
    ingest_parsed as _ingest_parsed,
)
from fleetent.knowledge_base.ingest.runtime import (
    ingest_text as _ingest_text,
)
from fleetent.knowledge_base.ingest.runtime import (
    iter_indexable_knowledge_chunks as _iter_indexable_chunks_impl,
)
from fleetent.knowledge_base.management.runtime import (
    archive_knowledge_base as _archive_knowledge_base,
)
from fleetent.knowledge_base.management.runtime import (
    create_knowledge_base as _create_knowledge_base,
)
from fleetent.knowledge_base.management.runtime import (
    is_active_knowledge_base as _is_active_knowledge_base,
)
from fleetent.knowledge_base.management.runtime import (
    list_documents as _list_documents_impl,
)
from fleetent.knowledge_base.management.runtime import (
    list_knowledge_bases as _list_knowledge_bases_impl,
)
from fleetent.knowledge_base.management.runtime import (
    preview_document_chunks as _preview_document_chunks_impl,
)
from fleetent.knowledge_base.management.runtime import (
    update_knowledge_base_description as _update_knowledge_base_description,
)
from fleetent.knowledge_base.retrieval import SearchMode
from fleetent.knowledge_base.retrieval.search import (
    RERANK_CANDIDATE_MAX,
    RERANK_CANDIDATE_MIN,
    RERANK_CANDIDATE_MULTIPLIER,
)
from fleetent.knowledge_base.retrieval.search import (
    _apply_rerank_results as _apply_rerank_results_impl,
)
from fleetent.knowledge_base.retrieval.search import (
    _search_hybrid as _search_hybrid_impl,
)
from fleetent.knowledge_base.retrieval.search import (
    _search_vector as _search_vector_impl,
)
from fleetent.knowledge_base.retrieval.search import (
    search as _search_chunks,
)
from fleetent.observability.structured_logging import get_logger
from fleetent.vector_store import rerank as rerank_runtime

_logger = get_logger("knowledge_base")


async def ingest_text(
    filename: str,
    content: str,
    tenant_id: str | None = None,
    kb_id: str | None = None,
    source: str = "manual",
    source_url: str | None = None,
) -> KnowledgeDocument:
    """Parse and ingest plain text using default KB settings."""

    return await _ingest_text(
        filename,
        content,
        tenant_id,
        kb_id,
        source,
        source_url,
        settings=_kb_config(),
        database=_database(),
    )


async def ingest_parsed(
    parsed: Any,
    tenant_id: str | None = None,
    kb_id: str | None = None,
    source: str = "manual",
    source_url: str | None = None,
) -> KnowledgeDocument:
    """Persist pre-parsed document sections using default KB settings."""

    return await _ingest_parsed(
        parsed,
        tenant_id,
        kb_id,
        source,
        source_url,
        settings=_kb_config(),
        database=_database(),
    )


async def search(
    query: str,
    tenant_id: str | None = None,
    kb_ids: list[str] | None = None,
    limit: int = 10,
    mode: SearchMode = "vector",
    rerank: bool = False,
) -> list[KnowledgeChunk]:
    """Search KB chunks using default store and default KB config."""

    return await _search_chunks(
        query,
        store=KnowledgeStore(_database()),
        tenant_id=tenant_id,
        kb_ids=kb_ids,
        limit=limit,
        mode=mode,
        rerank=rerank,
    )


async def _search_vector(
    query: str,
    tenant_id: str,
    kb_ids: list[str],
    limit: int,
    store: KnowledgeStore,
) -> list[KnowledgeChunk]:
    return await _search_vector_impl(query, tenant_id, kb_ids, limit, store)


async def _search_hybrid(
    query: str,
    tenant_id: str,
    kb_ids: list[str],
    limit: int,
    store: KnowledgeStore,
    rerank: bool = False,
) -> list[KnowledgeChunk]:
    return await _search_hybrid_impl(
        query,
        tenant_id,
        kb_ids,
        limit,
        store,
        rerank=rerank,
    )


def _rerank_candidate_limit(limit: int) -> int:
    return min(
        max(limit * RERANK_CANDIDATE_MULTIPLIER, RERANK_CANDIDATE_MIN),
        RERANK_CANDIDATE_MAX,
    )


async def _rerank_hybrid_candidates(
    query: str,
    candidates: list[KnowledgeChunk],
    *,
    tenant_id: str,
    kb_ids: list[str],
    limit: int,
) -> list[KnowledgeChunk]:
    provider = rerank_runtime.create_rerank_provider(_rerank_settings())
    try:
        results = await provider.rerank(
            query,
            [candidate.content for candidate in candidates],
            top_n=limit,
        )
    except Exception as exc:  # pragma: no cover - error path covered by unit tests
        reason = str(exc) or exc.__class__.__name__
        _logger.warn(
            "kb_rerank_failed",
            tenant_id=tenant_id,
            kb_ids=kb_ids,
            limit=limit,
            candidate_count=len(candidates),
            reason=reason,
        )
        return candidates[:limit]

    return _apply_rerank_results(candidates, results, limit)


def _apply_rerank_results(
    candidates: list[KnowledgeChunk],
    results: list[rerank_runtime.RerankResult],
    limit: int,
) -> list[KnowledgeChunk]:
    return _apply_rerank_results_impl(candidates, results, limit)


async def archive(document_id: str) -> None:
    """Archive one document and remove chunk index records."""

    return await _archive_document(document_id, database=_database())


async def archive_knowledge_base(tenant_id: str, kb_id: str) -> bool:
    """Archive a KB and remove active chunks from vector index."""

    return await _archive_knowledge_base(tenant_id, kb_id)


def create_knowledge_base(tenant_id: str, kb_id: str, description: str = "") -> None:
    """Create a KB entry if it does not already exist."""

    return _create_knowledge_base(tenant_id, kb_id, description, database=_database())


def update_knowledge_base_description(tenant_id: str, kb_id: str, description: str) -> bool:
    """Update a KB description field."""

    return _update_knowledge_base_description(
        tenant_id,
        kb_id,
        description,
        database=_database(),
    )


def is_active_knowledge_base(tenant_id: str, kb_id: str) -> bool:
    """Return whether KB exists and is not archived."""

    return _is_active_knowledge_base(tenant_id, kb_id, database=_database())


async def delete(document_id: str) -> None:
    """Delete a KB document and any scope-bound chunks."""

    return await _delete_document(document_id, database=_database())


async def delete_document(tenant_id: str, kb_id: str, document_id: str) -> bool:
    """Delete one scoped KB document."""

    return await _delete_scoped_document(tenant_id, kb_id, document_id, database=_database())


def iter_indexable_knowledge_chunks(
    tenant_id: str,
    kb_id: str,
) -> Iterator[vector_store.IndexableItem]:
    """Yield indexable chunks for vector sync/rebuild flows."""

    return _iter_indexable_chunks_impl(tenant_id, kb_id, database=_database())


def list_knowledge_bases(tenant_id: str) -> list[dict[str, object]]:
    """List KB metadata rows for one tenant."""

    rows = list(_list_knowledge_bases_impl(tenant_id))
    return [
        {
            "tenant_id": str(row["tenant_id"]),
            "kb_id": str(row["kb_id"]),
            "description": str(row["description"]),
            "doc_count": int(row["doc_count"]),
            "chunk_count": int(row["chunk_count"]),
            "last_import": row["last_import"],
            "archived": row["archived_at"] is not None,
        }
        for row in rows
    ]


def list_documents(tenant_id: str, kb_id: str) -> list[dict[str, object]]:
    """List active KB documents in one tenant and KB."""

    return [
        {
            "document_id": str(row["document_id"]),
            "filename": str(row["filename"]),
            "source": str(row["source"]),
            "source_url": row["source_url"],
            "chunks": int(row["chunks"]),
            "created_at": row["created_at"],
        }
        for row in _list_documents_impl(tenant_id, kb_id)
    ]


def preview_document_chunks(
    tenant_id: str,
    kb_id: str,
    document_id: str,
) -> list[dict[str, object]]:
    """Return public chunk snapshots for a document."""

    chunks = _preview_document_chunks_impl(
        tenant_id,
        kb_id,
        document_id,
        database=_database(),
    )
    return [_chunk_to_public_dict(chunk) for chunk in chunks]


def _chunk_to_public_dict(chunk: KnowledgeChunk) -> dict[str, object]:
    return {
        "chunk_id": chunk.id,
        "document_id": chunk.document_id,
        "kb_id": chunk.kb_id,
        "filename": chunk.filename,
        "content": chunk.content,
        "position": chunk.position,
        "score": chunk.score,
        "source": chunk.source,
        "source_url": chunk.source_url,
        "section": chunk.metadata.get("section_title") or chunk.metadata.get("section_path", ""),
        "section_path": chunk.metadata.get("section_path", ""),
    }


def _kb_config() -> KnowledgeBaseSettings:
    return KnowledgeBaseSettings()


def _rerank_settings() -> Any:
    from fleetent import agent_config

    return agent_config.active_agent_or_default().rerank


def _settings() -> Settings:
    return Settings()


def _database() -> SQLiteDatabase:
    return create_database(_settings().database_url)


__all__ = [
    "vector_store",
    "SearchMode",
    "archive",
    "archive_knowledge_base",
    "create_knowledge_base",
    "delete",
    "delete_document",
    "ingest_parsed",
    "ingest_text",
    "is_active_knowledge_base",
    "iter_indexable_knowledge_chunks",
    "list_documents",
    "list_knowledge_bases",
    "preview_document_chunks",
    "search",
    "_search_hybrid",
    "_search_vector",
    "_rerank_candidate_limit",
    "_rerank_hybrid_candidates",
    "_apply_rerank_results",
    "RERANK_CANDIDATE_MULTIPLIER",
    "RERANK_CANDIDATE_MIN",
    "RERANK_CANDIDATE_MAX",
    "update_knowledge_base_description",
]
