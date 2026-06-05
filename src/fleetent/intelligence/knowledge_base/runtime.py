from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import replace
from typing import Literal

from fleetent.config import KnowledgeBaseSettings, RerankSettings, Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.intelligence import vector_store
from fleetent.intelligence.knowledge_base.models import KnowledgeChunk, KnowledgeDocument
from fleetent.intelligence.knowledge_base.parsers import ParsedDocument
from fleetent.intelligence.knowledge_base.store import KnowledgeStore
from fleetent.intelligence.vector_store import rerank as rerank_runtime
from fleetent.observability.structured_logging import get_logger

SearchMode = Literal["vector", "keyword", "hybrid"]
_SEARCH_MODES: set[str] = {"vector", "keyword", "hybrid"}
RERANK_CANDIDATE_MULTIPLIER = 5
RERANK_CANDIDATE_MIN = 20
RERANK_CANDIDATE_MAX = 100
_logger = get_logger("knowledge_base")


def create_knowledge_base(tenant_id: str, kb_id: str, description: str = "") -> None:
    """Create a tenant-scoped knowledge base record if it does not already exist."""

    KnowledgeStore(_database()).ensure_knowledge_base(tenant_id, kb_id, description)


def update_knowledge_base_description(tenant_id: str, kb_id: str, description: str) -> bool:
    """Update the description for a tenant-scoped knowledge base."""

    return KnowledgeStore(_database()).update_knowledge_base_description(
        tenant_id, kb_id, description
    )


def is_active_knowledge_base(tenant_id: str, kb_id: str) -> bool:
    """Return whether a knowledge base exists and is not archived."""

    return KnowledgeStore(_database()).has_active_knowledge_base(tenant_id, kb_id)


async def archive_knowledge_base(tenant_id: str, kb_id: str) -> bool:
    """Archive a knowledge base and remove its active chunks from vector indexes."""

    store = KnowledgeStore(_database())
    chunks = store.iter_indexable_chunks(tenant_id, kb_id)
    archived = store.archive_knowledge_base(tenant_id, kb_id)
    if not archived:
        return False
    for chunk in chunks:
        await vector_store.delete(
            chunk.id,
            vector_store.knowledge_namespace(chunk.tenant_id, chunk.kb_id),
        )
    return True


def list_knowledge_bases(tenant_id: str) -> list[dict[str, object]]:
    """List tenant knowledge bases with document and chunk aggregates."""

    rows = KnowledgeStore(_database()).list_knowledge_bases(tenant_id)
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
    """List active documents imported into one knowledge base."""

    rows = KnowledgeStore(_database()).list_documents(tenant_id, kb_id)
    return [
        {
            "document_id": str(row["document_id"]),
            "filename": str(row["filename"]),
            "source": str(row["source"]),
            "source_url": str(row["source_url"]) if row["source_url"] is not None else None,
            "chunks": int(row["chunks"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def preview_document_chunks(
    tenant_id: str, kb_id: str, document_id: str
) -> list[dict[str, object]]:
    """Return ordered chunk previews for one active document."""

    chunks = KnowledgeStore(_database()).preview_document_chunks(tenant_id, kb_id, document_id)
    return [_chunk_to_public_dict(chunk) for chunk in chunks]


async def ingest_text(
    filename: str,
    content: str,
    tenant_id: str | None = None,
    kb_id: str | None = None,
    source: str = "manual",
    source_url: str | None = None,
) -> KnowledgeDocument:
    """Import plain text or markdown content into a knowledge base."""

    normalized_content = content.strip()
    if not normalized_content:
        raise ValueError("content must not be empty")

    settings = _kb_config()
    chunks = [
        KnowledgeChunk(
            id="",
            document_id="",
            tenant_id="",
            kb_id="",
            filename=filename,
            content=chunk_content,
            position=position,
            score=0.0,
            source=source,
            source_url=source_url,
        )
        for position, chunk_content in enumerate(
            _chunk_text(normalized_content, settings.chunk_size, settings.chunk_overlap)
        )
    ]
    return await _ingest_chunks(
        filename=filename,
        chunks=chunks,
        tenant_id=tenant_id,
        kb_id=kb_id,
        source=source,
        source_url=source_url,
    )


async def ingest_parsed(
    parsed: ParsedDocument,
    tenant_id: str | None = None,
    kb_id: str | None = None,
    source: str = "manual",
    source_url: str | None = None,
) -> KnowledgeDocument:
    """Import parsed document sections into a knowledge base."""

    settings = _kb_config()
    chunks: list[KnowledgeChunk] = []
    position = 0
    for section in parsed.sections:
        normalized_text = section.text.strip()
        if not normalized_text:
            continue
        section_metadata = {
            "document_format": parsed.format,
            "section_level": str(section.level),
            "section_path": section.metadata.get("path", section.title),
            "section_title": section.title,
        }
        for key, value in section.metadata.items():
            if key != "path":
                section_metadata[key] = value
        for chunk_content in _chunk_text(
            normalized_text, settings.chunk_size, settings.chunk_overlap
        ):
            chunks.append(
                KnowledgeChunk(
                    id="",
                    document_id="",
                    tenant_id="",
                    kb_id="",
                    filename=parsed.filename,
                    content=chunk_content,
                    position=position,
                    score=0.0,
                    source=source,
                    source_url=source_url,
                    metadata=section_metadata,
                )
            )
            position += 1
    if not chunks:
        raise ValueError("content must not be empty")

    return await _ingest_chunks(
        filename=parsed.filename,
        chunks=chunks,
        tenant_id=tenant_id,
        kb_id=kb_id,
        source=source,
        source_url=source_url,
    )


async def _ingest_chunks(
    filename: str,
    chunks: list[KnowledgeChunk],
    tenant_id: str | None,
    kb_id: str | None,
    source: str,
    source_url: str | None,
) -> KnowledgeDocument:
    settings = _kb_config()
    resolved_tenant_id = tenant_id or settings.default_tenant_id
    resolved_kb_id = kb_id or settings.default_kb_id
    document = KnowledgeDocument(
        id=str(uuid.uuid4()),
        tenant_id=resolved_tenant_id,
        kb_id=resolved_kb_id,
        filename=filename,
        source=source,
        source_url=source_url,
    )
    resolved_chunks = [
        KnowledgeChunk(
            id=f"{document.id}:chunk:{position}",
            document_id=document.id,
            tenant_id=document.tenant_id,
            kb_id=document.kb_id,
            filename=document.filename,
            content=chunk.content,
            position=position,
            score=chunk.score,
            source=document.source,
            source_url=document.source_url,
            metadata=chunk.metadata,
        )
        for position, chunk in enumerate(chunks)
    ]
    store = KnowledgeStore(_database())
    store.ensure_knowledge_base(document.tenant_id, document.kb_id)
    store.insert_document(document)
    store.insert_chunks(resolved_chunks)
    namespace = vector_store.knowledge_namespace(document.tenant_id, document.kb_id)
    for chunk in resolved_chunks:
        await vector_store.upsert(chunk.id, chunk.content, namespace)
    return document


async def search(
    query: str,
    tenant_id: str | None = None,
    kb_ids: list[str] | None = None,
    limit: int = 10,
    mode: SearchMode = "vector",
    rerank: bool = False,
) -> list[KnowledgeChunk]:
    """Search knowledge chunks using vector, keyword, or hybrid retrieval."""

    if mode not in _SEARCH_MODES:
        raise ValueError(f"unsupported knowledge search mode: {mode}")
    if rerank and mode != "hybrid":
        raise ValueError("rerank only supports hybrid knowledge search mode")
    if limit <= 0:
        return []

    settings = _kb_config()
    resolved_tenant_id = tenant_id or settings.default_tenant_id
    resolved_kb_ids = kb_ids or [settings.default_kb_id]
    store = KnowledgeStore(_database())
    if mode == "keyword":
        return store.search_keyword(query, resolved_tenant_id, resolved_kb_ids, limit)
    if mode == "hybrid":
        return await _search_hybrid(
            query,
            resolved_tenant_id,
            resolved_kb_ids,
            limit,
            store,
            rerank=rerank,
        )

    return await _search_vector(query, resolved_tenant_id, resolved_kb_ids, limit, store)


async def _search_vector(
    query: str,
    tenant_id: str,
    kb_ids: list[str],
    limit: int,
    store: KnowledgeStore,
) -> list[KnowledgeChunk]:
    score_by_id: dict[str, float] = {}
    for kb_id in kb_ids:
        namespace = vector_store.knowledge_namespace(tenant_id, kb_id)
        vector_results = await vector_store.search(query, namespace, limit)
        for result in vector_results:
            score_by_id[result.id] = max(score_by_id.get(result.id, result.score), result.score)

    chunks = store.get_chunks_by_ids(tenant_id, list(score_by_id))
    requested_kbs = set(kb_ids)
    scored_chunks = [
        replace(chunk, score=score_by_id[chunk.id])
        for chunk in chunks
        if chunk.kb_id in requested_kbs
    ]
    return sorted(
        scored_chunks,
        key=lambda chunk: (-chunk.score, chunk.position, chunk.id),
    )[:limit]


async def _search_hybrid(
    query: str,
    tenant_id: str,
    kb_ids: list[str],
    limit: int,
    store: KnowledgeStore,
    *,
    rerank: bool = False,
) -> list[KnowledgeChunk]:
    candidate_limit = _rerank_candidate_limit(limit) if rerank else limit
    vector_chunks = await _search_vector(query, tenant_id, kb_ids, candidate_limit, store)
    keyword_chunks = store.search_keyword(query, tenant_id, kb_ids, candidate_limit)
    chunk_by_id = {chunk.id: chunk for chunk in vector_chunks}
    chunk_by_id.update({chunk.id: chunk for chunk in keyword_chunks})

    rrf_scores: dict[str, float] = {}
    for rank, chunk in enumerate(vector_chunks, start=1):
        rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + _rrf_score(rank)
    for rank, chunk in enumerate(keyword_chunks, start=1):
        rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + _rrf_score(rank)

    fused = [
        replace(chunk_by_id[chunk_id], score=score)
        for chunk_id, score in rrf_scores.items()
        if chunk_id in chunk_by_id
    ]
    candidates = sorted(fused, key=lambda chunk: (-chunk.score, chunk.position, chunk.id))
    if not rerank:
        return candidates[:limit]
    return await _rerank_hybrid_candidates(
        query,
        candidates[:candidate_limit],
        tenant_id=tenant_id,
        kb_ids=kb_ids,
        limit=limit,
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
    provider = rerank_runtime.create_rerank_provider(_rerank_config())
    try:
        results = await provider.rerank(
            query,
            [candidate.content for candidate in candidates],
            top_n=limit,
        )
    except Exception as exc:
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
    selected: list[KnowledgeChunk] = []
    selected_indexes: set[int] = set()
    for result in results:
        if result.index < 0 or result.index >= len(candidates):
            continue
        if result.index in selected_indexes:
            continue
        selected_indexes.add(result.index)
        selected.append(replace(candidates[result.index], score=result.score))
        if len(selected) >= limit:
            return selected

    for index, candidate in enumerate(candidates):
        if index not in selected_indexes:
            selected.append(candidate)
        if len(selected) >= limit:
            break

    return selected


async def delete(document_id: str) -> None:
    """Delete a knowledge document, its chunks, and vector index entries."""

    store = KnowledgeStore(_database())
    chunks = store.get_document_chunks(document_id)
    for chunk in chunks:
        await vector_store.delete(
            chunk.id,
            vector_store.knowledge_namespace(chunk.tenant_id, chunk.kb_id),
        )
    store.delete_document(document_id)


async def delete_document(tenant_id: str, kb_id: str, document_id: str) -> bool:
    """Delete an active document only when it belongs to the given tenant and KB."""

    store = KnowledgeStore(_database())
    if not store.has_active_document(tenant_id, kb_id, document_id):
        return False
    chunks = store.get_scoped_document_chunks(tenant_id, kb_id, document_id)
    for chunk in chunks:
        await vector_store.delete(
            chunk.id,
            vector_store.knowledge_namespace(chunk.tenant_id, chunk.kb_id),
        )
    return store.delete_scoped_document(tenant_id, kb_id, document_id)


async def archive(document_id: str) -> None:
    """Archive a knowledge document without deleting the document record."""

    store = KnowledgeStore(_database())
    chunks = store.get_document_chunks(document_id)
    for chunk in chunks:
        await vector_store.delete(
            chunk.id,
            vector_store.knowledge_namespace(chunk.tenant_id, chunk.kb_id),
        )
    store.archive_document(document_id)


def iter_indexable_knowledge_chunks(
    tenant_id: str, kb_id: str
) -> Iterator[vector_store.IndexableItem]:
    """Yield current knowledge chunks that should exist in vector_store."""
    namespace = vector_store.knowledge_namespace(tenant_id, kb_id)
    store = KnowledgeStore(_database())
    for chunk in store.iter_indexable_chunks(tenant_id, kb_id):
        metadata = {
            "document_id": chunk.document_id,
            "filename": chunk.filename,
            "source": chunk.source,
        }
        if chunk.source_url is not None:
            metadata["source_url"] = chunk.source_url
        yield vector_store.IndexableItem(
            id=chunk.id,
            content=chunk.content,
            namespace=namespace,
            metadata=metadata,
        )


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


def _chunk_text(content: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")

    step = chunk_size - chunk_overlap
    chunks: list[str] = []
    for start in range(0, len(content), step):
        chunk = content[start : start + chunk_size]
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(content):
            break
    return chunks


def _settings() -> Settings:
    return Settings()


def _kb_config() -> KnowledgeBaseSettings:
    """Neutral KB runtime defaults; source construction lives in knowledge.yaml."""
    return KnowledgeBaseSettings()


def _rerank_config() -> RerankSettings:
    """rerank config from the active agent (a neutral default when absent)."""
    from fleetent import agent_config

    return agent_config.active_agent_or_default().rerank


def _database() -> SQLiteDatabase:
    return create_database(_settings().database_url)


def _rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)
