import uuid
from dataclasses import replace

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.intelligence import vector_store
from fleetent.intelligence.knowledge_base.models import KnowledgeChunk, KnowledgeDocument
from fleetent.intelligence.knowledge_base.parsers import ParsedDocument
from fleetent.intelligence.knowledge_base.store import KnowledgeStore


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

    settings = _settings().knowledge_base
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

    settings = _settings().knowledge_base
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
    settings = _settings().knowledge_base
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
) -> list[KnowledgeChunk]:
    """Search knowledge chunks using vector-only retrieval."""

    if limit <= 0:
        return []

    settings = _settings().knowledge_base
    resolved_tenant_id = tenant_id or settings.default_tenant_id
    resolved_kb_ids = kb_ids or [settings.default_kb_id]
    store = KnowledgeStore(_database())
    score_by_id: dict[str, float] = {}
    for kb_id in resolved_kb_ids:
        namespace = vector_store.knowledge_namespace(resolved_tenant_id, kb_id)
        vector_results = await vector_store.search(query, namespace, limit)
        for result in vector_results:
            score_by_id[result.id] = max(score_by_id.get(result.id, result.score), result.score)

    chunks = store.get_chunks_by_ids(resolved_tenant_id, list(score_by_id))
    requested_kbs = set(resolved_kb_ids)
    scored_chunks = [
        replace(chunk, score=score_by_id[chunk.id])
        for chunk in chunks
        if chunk.kb_id in requested_kbs
    ]
    return sorted(
        scored_chunks,
        key=lambda chunk: (-chunk.score, chunk.position, chunk.id),
    )[:limit]


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
    return Settings(anthropic_api_key="")


def _database() -> SQLiteDatabase:
    return create_database(_settings().database_url)
