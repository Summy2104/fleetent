"""Type-layer Protocol contracts for knowledge-base read/write boundaries.

Consumers:
- retrieval/ functions accept KnowledgeReadable — write methods intentionally invisible
- ingest/ and management/ accept KnowledgeWritable
- KnowledgeStore (core/store.py) satisfies both via structural subtyping (no inheritance)
"""

from typing import Any, Protocol, runtime_checkable

from fleetent.db import Row

from .models import KnowledgeChunk, KnowledgeDocument


@runtime_checkable
class KnowledgeReadable(Protocol):
    """Read-only store API for knowledge-base entities."""

    def has_active_knowledge_base(self, tenant_id: str, kb_id: str) -> bool: ...

    def list_knowledge_bases(self, tenant_id: str) -> list[Row]: ...

    def get_chunks_by_ids(self, tenant_id: str, chunk_ids: list[str]) -> list[KnowledgeChunk]: ...

    def get_document_chunks(self, document_id: str) -> list[KnowledgeChunk]: ...

    def get_scoped_document_chunks(
        self, tenant_id: str, kb_id: str, document_id: str
    ) -> list[KnowledgeChunk]: ...

    def has_active_document(self, tenant_id: str, kb_id: str, document_id: str) -> bool: ...

    def iter_indexable_chunks(self, tenant_id: str, kb_id: str) -> list[KnowledgeChunk]: ...

    def list_documents(self, tenant_id: str, kb_id: str) -> list[Row]: ...

    def preview_document_chunks(
        self, tenant_id: str, kb_id: str, document_id: str
    ) -> list[KnowledgeChunk]: ...

    def search_keyword(
        self, query: str, tenant_id: str, kb_ids: list[str], limit: int
    ) -> list[KnowledgeChunk]: ...


@runtime_checkable
class KnowledgeWritable(Protocol):
    """Write-only mutations for knowledge-base stores."""

    def ensure_knowledge_base(
        self,
        tenant_id: str,
        kb_id: str,
        description: str = "",
        *,
        extraction_enabled: bool = False,
    ) -> None: ...

    def update_knowledge_base_description(
        self, tenant_id: str, kb_id: str, description: str
    ) -> bool: ...

    def archive_knowledge_base(self, tenant_id: str, kb_id: str) -> bool: ...

    def insert_document(self, document: KnowledgeDocument) -> None: ...

    def insert_chunks(self, chunks: list[KnowledgeChunk]) -> None: ...

    def archive_document(self, document_id: str) -> None: ...

    def delete_document(self, document_id: str) -> None: ...

    def delete_scoped_document(self, tenant_id: str, kb_id: str, document_id: str) -> bool: ...


__all__: list[Any] = [
    "KnowledgeReadable",
    "KnowledgeWritable",
]
