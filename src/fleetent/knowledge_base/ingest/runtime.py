from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping, Sequence
from typing import Protocol

from fleetent import vector_store
from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.knowledge_base.core import KnowledgeChunk, KnowledgeDocument, KnowledgeStore
from fleetent.vector_store.backend import VectorBackend


class _ParsedSectionLike(Protocol):
    @property
    def text(self) -> str: ...

    @property
    def level(self) -> int: ...

    @property
    def title(self) -> str: ...

    @property
    def metadata(self) -> Mapping[str, object]: ...


class _ParsedDocumentLike(Protocol):
    @property
    def filename(self) -> str: ...

    @property
    def format(self) -> str: ...

    @property
    def sections(self) -> Sequence[_ParsedSectionLike]: ...


async def ingest_text(
    filename: str,
    content: str,
    tenant_id: str | None,
    kb_id: str | None,
    source: str,
    source_url: str | None,
    settings: KnowledgeBaseSettings,
    database: SQLiteDatabase | None = None,
) -> KnowledgeDocument:
    """Import plain text content into a knowledge base."""
    normalized_content = content.strip()
    if not normalized_content:
        raise ValueError("content must not be empty")

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
        settings=settings,
        database=database,
    )


async def ingest_parsed(
    parsed: _ParsedDocumentLike,
    tenant_id: str | None,
    kb_id: str | None,
    source: str,
    source_url: str | None,
    settings: KnowledgeBaseSettings,
    database: SQLiteDatabase | None = None,
) -> KnowledgeDocument:
    """Import parsed document sections into a knowledge base."""
    chunks: list[KnowledgeChunk] = []
    position = 0
    for section in parsed.sections:
        normalized_text = section.text.strip()
        if not normalized_text:
            continue
        section_metadata: dict[str, str] = {
            "document_format": parsed.format,
            "section_level": str(section.level),
            "section_path": str(section.metadata.get("path", section.title)),
            "section_title": section.title,
        }
        for key, value in section.metadata.items():
            if key != "path":
                section_metadata[key] = str(value)
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
        settings=settings,
        database=database,
    )


async def _ingest_chunks(
    filename: str,
    chunks: list[KnowledgeChunk],
    tenant_id: str | None,
    kb_id: str | None,
    source: str,
    source_url: str | None,
    settings: KnowledgeBaseSettings,
    database: SQLiteDatabase | None = None,
) -> KnowledgeDocument:
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
    store = KnowledgeStore(_database_or_default(database))
    store.ensure_knowledge_base(document.tenant_id, document.kb_id)
    existing_documents = store.list_active_documents_by_identity(
        document.tenant_id,
        document.kb_id,
        document.source,
        document.filename,
    )
    replaced_document_ids = [existing_document.id for existing_document in existing_documents]
    replaced_chunks = [
        chunk
        for existing_document in existing_documents
        for chunk in store.get_document_chunks(existing_document.id)
    ]
    store.replace_document(document, resolved_chunks, replaced_document_ids)
    for chunk in replaced_chunks:
        await _delete_chunk(
            vector_store.knowledge_namespace(chunk.tenant_id, chunk.kb_id),
            chunk.id,
        )
    namespace = vector_store.knowledge_namespace(document.tenant_id, document.kb_id)
    for chunk in resolved_chunks:
        await _upsert_chunk(namespace, chunk)
    return document


async def delete(document_id: str, database: SQLiteDatabase | None = None) -> None:
    """Delete a knowledge document, its chunks, and vector index entries."""

    store = KnowledgeStore(_database_or_default(database))
    chunks = store.get_document_chunks(document_id)
    for chunk in chunks:
        await _delete_chunk(
            vector_store.knowledge_namespace(chunk.tenant_id, chunk.kb_id),
            chunk.id,
        )
    store.delete_document(document_id)


async def delete_document(
    tenant_id: str,
    kb_id: str,
    document_id: str,
    database: SQLiteDatabase | None = None,
) -> bool:
    """Delete an active document only when it belongs to given tenant and KB."""

    store = KnowledgeStore(_database_or_default(database))
    if not store.has_active_document(tenant_id, kb_id, document_id):
        return False
    chunks = store.get_scoped_document_chunks(tenant_id, kb_id, document_id)
    for chunk in chunks:
        await _delete_chunk(
            vector_store.knowledge_namespace(chunk.tenant_id, chunk.kb_id),
            chunk.id,
        )
    return store.delete_scoped_document(tenant_id, kb_id, document_id)


async def archive(document_id: str, database: SQLiteDatabase | None = None) -> None:
    """Archive a knowledge document without deleting its document record."""

    store = KnowledgeStore(_database_or_default(database))
    chunks = store.get_document_chunks(document_id)
    for chunk in chunks:
        await _delete_chunk(
            vector_store.knowledge_namespace(chunk.tenant_id, chunk.kb_id),
            chunk.id,
        )
    store.archive_document(document_id)


def iter_indexable_knowledge_chunks(
    tenant_id: str,
    kb_id: str,
    database: SQLiteDatabase | None = None,
) -> Iterator[vector_store.IndexableItem]:
    """Yield indexable chunks that should currently exist in vector store."""
    namespace = vector_store.knowledge_namespace(tenant_id, kb_id)
    store = KnowledgeStore(_database_or_default(database))
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


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _database_or_default(database: SQLiteDatabase | None) -> SQLiteDatabase:
    return database if database is not None else _database()


async def _upsert_chunk(namespace: str, chunk: KnowledgeChunk) -> None:
    backend = _injected_vector_backend()
    if backend is None:
        await vector_store.upsert(chunk.id, chunk.content, namespace)
        return
    await backend.upsert(chunk.id, await vector_store.embed_text(chunk.content), namespace)


async def _delete_chunk(namespace: str, chunk_id: str) -> None:
    backend = _injected_vector_backend()
    if backend is None:
        await vector_store.delete(chunk_id, namespace)
        return
    await backend.delete(chunk_id, namespace)


def _injected_vector_backend() -> VectorBackend | None:
    from fleetent.knowledge_base import runtime

    try:
        return runtime._vector_backend()
    except RuntimeError:
        return None
