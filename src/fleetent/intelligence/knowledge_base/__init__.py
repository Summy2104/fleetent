"""Knowledge-base runtime public API."""

from fleetent.intelligence.knowledge_base.models import KnowledgeChunk, KnowledgeDocument
from fleetent.intelligence.knowledge_base.parsers import (
    ParsedDocument,
    ParsedSection,
    parse_html,
    parse_markdown,
    parse_text,
)
from fleetent.intelligence.knowledge_base.runtime import delete, ingest_parsed, ingest_text, search

__all__ = [
    "KnowledgeChunk",
    "KnowledgeDocument",
    "ParsedDocument",
    "ParsedSection",
    "delete",
    "ingest_parsed",
    "ingest_text",
    "parse_html",
    "parse_markdown",
    "parse_text",
    "search",
]
