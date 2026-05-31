"""Knowledge-base runtime public API."""

from fleetent.intelligence.knowledge_base.models import KnowledgeChunk, KnowledgeDocument
from fleetent.intelligence.knowledge_base.runtime import delete, ingest_text, search

__all__ = [
    "KnowledgeChunk",
    "KnowledgeDocument",
    "delete",
    "ingest_text",
    "search",
]
