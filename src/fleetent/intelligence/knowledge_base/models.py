from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeDocument:
    """Document imported into a tenant-scoped knowledge base."""

    id: str
    tenant_id: str
    kb_id: str
    filename: str
    source: str
    source_url: str | None


@dataclass(frozen=True)
class KnowledgeChunk:
    """Searchable chunk belonging to an imported knowledge document."""

    id: str
    document_id: str
    tenant_id: str
    kb_id: str
    filename: str
    content: str
    position: int
    score: float
    source: str
    source_url: str | None
