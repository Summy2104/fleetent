"""Knowledge-base runtime public API."""

from fleetent.intelligence.knowledge_base.models import KnowledgeChunk, KnowledgeDocument
from fleetent.intelligence.knowledge_base.parsers import (
    ParsedDocument,
    ParsedSection,
    parse_html,
    parse_markdown,
    parse_text,
)
from fleetent.intelligence.knowledge_base.runtime import (
    delete,
    ingest_parsed,
    ingest_text,
    iter_indexable_knowledge_chunks,
    search,
)
from fleetent.intelligence.knowledge_base.sync_planner import (
    SyncAction,
    SyncExecutionSummary,
    SyncPlan,
    SyncPlanItem,
    SyncPlanSummary,
    execute_sync_plan,
    plan_local_directory_sync,
)

__all__ = [
    "KnowledgeChunk",
    "KnowledgeDocument",
    "ParsedDocument",
    "ParsedSection",
    "SyncAction",
    "SyncExecutionSummary",
    "SyncPlan",
    "SyncPlanItem",
    "SyncPlanSummary",
    "delete",
    "execute_sync_plan",
    "ingest_parsed",
    "ingest_text",
    "iter_indexable_knowledge_chunks",
    "parse_html",
    "parse_markdown",
    "parse_text",
    "plan_local_directory_sync",
    "search",
]
