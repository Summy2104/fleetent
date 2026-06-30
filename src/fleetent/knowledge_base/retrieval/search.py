from __future__ import annotations

import time
from dataclasses import replace
from typing import Literal, Protocol

from fleetent import agent_config, vector_store
from fleetent.config import KnowledgeBaseSettings, RerankSettings
from fleetent.knowledge_base.core import KnowledgeChunk, KnowledgeReadable
from fleetent.knowledge_base.errors import (
    KnowledgeBaseEmbeddingMismatchError,
    embedding_mismatch_message,
)
from fleetent.observability import KBRetrievalAuditContext, record_kb_retrieval
from fleetent.vector_store import rerank as rerank_runtime

SearchMode = Literal["vector", "keyword", "hybrid"]
_SEARCH_MODES: set[str] = {"vector", "keyword", "hybrid"}
RERANK_CANDIDATE_MULTIPLIER = 5
RERANK_CANDIDATE_MIN = 20
RERANK_CANDIDATE_MAX = 100


class LoggerProtocol(Protocol):
    def warn(self, message: str, **fields: object) -> None: ...


def _logger() -> LoggerProtocol:
    from fleetent.structured_logging import get_logger

    return get_logger("knowledge_base")


async def search(
    query: str,
    store: KnowledgeReadable,
    tenant_id: str | None = None,
    kb_ids: list[str] | None = None,
    limit: int = 10,
    mode: SearchMode = "vector",
    rerank: bool = False,
    audit_context: KBRetrievalAuditContext | None = None,
) -> list[KnowledgeChunk]:
    """Search knowledge chunks using vector, keyword, or hybrid retrieval."""

    if mode not in _SEARCH_MODES:
        raise ValueError(f"unsupported knowledge search mode: {mode}")
    if rerank and mode != "hybrid":
        raise ValueError("rerank only supports hybrid knowledge search mode")
    if limit <= 0:
        return []

    settings = _scope_settings()
    resolved_tenant_id = tenant_id or settings.default_tenant_id
    resolved_kb_ids = kb_ids or [settings.default_kb_id]
    start = time.monotonic()
    if mode == "keyword":
        results = store.search_keyword(query, resolved_tenant_id, resolved_kb_ids, limit)
    elif mode == "hybrid":
        results = await _search_hybrid(
            query,
            resolved_tenant_id,
            resolved_kb_ids,
            limit,
            store,
            rerank=rerank,
        )
    else:
        results = await _search_vector(query, resolved_tenant_id, resolved_kb_ids, limit, store)
    latency_ms = (time.monotonic() - start) * 1000.0
    _record_search_audit(
        audit_context,
        query=query,
        results=results,
        latency_ms=latency_ms,
        mode=mode,
        kb_ids=resolved_kb_ids,
    )
    return results


def _record_search_audit(
    audit_context: KBRetrievalAuditContext | None,
    *,
    query: str,
    results: list[KnowledgeChunk],
    latency_ms: float,
    mode: str,
    kb_ids: list[str],
) -> None:
    if audit_context is None:
        return
    try:
        record_kb_retrieval(
            audit_context,
            query=query,
            results=results,
            latency_ms=latency_ms,
            mode=mode,
            kb_ids=kb_ids,
            plaintext=_audit_plaintext_enabled(),
        )
    except Exception as exc:  # noqa: BLE001 — side channel; never break retrieval
        _logger().warn(
            "kb_retrieval_audit_failed",
            run_id=audit_context.run_id,
            mode=mode,
            error=str(exc),
        )


def _audit_plaintext_enabled() -> bool:
    audit = getattr(agent_config.active_agent_or_default().knowledge, "retrieval_audit", None)
    if audit is not None and hasattr(audit, "plaintext"):
        return bool(audit.plaintext)
    return bool(_scope_settings().retrieval_audit.plaintext)


async def _search_vector(
    query: str,
    tenant_id: str,
    kb_ids: list[str],
    limit: int,
    store: KnowledgeReadable,
) -> list[KnowledgeChunk]:
    _validate_embedding_identity(store, tenant_id, kb_ids)
    query_vector = await vector_store.embed_text(query)
    backend = _vector_backend()
    score_by_id: dict[str, float] = {}
    for kb_id in kb_ids:
        namespace = vector_store.knowledge_namespace(tenant_id, kb_id)
        vector_results = await backend.search(query_vector, namespace, limit)
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


def _validate_embedding_identity(
    store: KnowledgeReadable, tenant_id: str, kb_ids: list[str]
) -> None:
    current = vector_store.current_embedding_identity()
    for kb_id in kb_ids:
        existing = store.get_embedding_identity(tenant_id, kb_id)
        if existing is None:
            continue
        expected_model, expected_dimensions = existing
        if expected_model == current.model and expected_dimensions == current.dimensions:
            continue
        raise KnowledgeBaseEmbeddingMismatchError(
            embedding_mismatch_message(
                tenant_id=tenant_id,
                kb_id=kb_id,
                expected_model=expected_model,
                expected_dimensions=expected_dimensions,
                current_model=current.model,
                current_dimensions=current.dimensions,
                operation="retrieval",
            )
        )


async def _search_hybrid(
    query: str,
    tenant_id: str,
    kb_ids: list[str],
    limit: int,
    store: KnowledgeReadable,
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
        _logger().warn(
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


def _scope_settings() -> KnowledgeBaseSettings:
    from fleetent.knowledge_base.retrieval._settings import kb_config

    return kb_config()


def _rerank_config() -> RerankSettings:
    from fleetent import agent_config

    return agent_config.active_agent_or_default().rerank


def _vector_backend():
    from fleetent.knowledge_base import runtime

    return runtime._vector_backend()


def _rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)
