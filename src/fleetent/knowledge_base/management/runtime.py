"""Knowledge-base management-layer runtime primitives."""

from __future__ import annotations

from collections.abc import Iterator

from fleetent import vector_store
from fleetent.config import Settings
from fleetent.db import Row, SQLiteDatabase, create_database
from fleetent.knowledge_base.core import KnowledgeChunk, KnowledgeStore


def create_knowledge_base(
    tenant_id: str,
    kb_id: str,
    description: str = "",
    database: SQLiteDatabase | None = None,
) -> None:
    """Create a tenant-scoped knowledge base if absent."""

    KnowledgeStore(_database_or_default(database)).ensure_knowledge_base(
        tenant_id, kb_id, description
    )


def update_knowledge_base_description(
    tenant_id: str, kb_id: str, description: str, database: SQLiteDatabase | None = None
) -> bool:
    """Update a KB description; return whether an existing KB was updated."""

    return KnowledgeStore(_database_or_default(database)).update_knowledge_base_description(
        tenant_id,
        kb_id,
        description,
    )


def is_active_knowledge_base(
    tenant_id: str, kb_id: str, database: SQLiteDatabase | None = None
) -> bool:
    """Return whether KB exists and is not archived."""

    return KnowledgeStore(_database_or_default(database)).has_active_knowledge_base(
        tenant_id, kb_id
    )


async def archive_knowledge_base(
    tenant_id: str, kb_id: str, database: SQLiteDatabase | None = None
) -> bool:
    """Archive a knowledge base and remove active chunks from the vector index."""

    store = KnowledgeStore(_database_or_default(database))
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


def list_knowledge_bases(tenant_id: str, database: SQLiteDatabase | None = None) -> list[Row]:
    """List KB rows for one tenant from storage."""

    return KnowledgeStore(_database_or_default(database)).list_knowledge_bases(tenant_id)


def list_documents(tenant_id: str, kb_id: str, database: SQLiteDatabase | None = None) -> list[Row]:
    """List active documents for a KB."""

    return KnowledgeStore(_database_or_default(database)).list_documents(tenant_id, kb_id)


def preview_document_chunks(
    tenant_id: str,
    kb_id: str,
    document_id: str,
    database: SQLiteDatabase | None = None,
) -> list[KnowledgeChunk]:
    """Return ordered chunk models for one document."""

    return KnowledgeStore(_database_or_default(database)).preview_document_chunks(
        tenant_id, kb_id, document_id
    )


def iter_indexable_chunks(
    tenant_id: str, kb_id: str, database: SQLiteDatabase | None = None
) -> Iterator[KnowledgeChunk]:
    """Yield indexable chunks for a KB from store."""

    return iter(
        KnowledgeStore(_database_or_default(database)).iter_indexable_chunks(tenant_id, kb_id)
    )


def _database() -> SQLiteDatabase:
    return create_database(_settings().database_url)


def _settings() -> Settings:
    return Settings()


def _database_or_default(database: SQLiteDatabase | None) -> SQLiteDatabase:
    return database if database is not None else _database()
