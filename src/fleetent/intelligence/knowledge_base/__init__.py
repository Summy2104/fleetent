"""Knowledge-base runtime public API."""

from fleetent.intelligence.knowledge_base.bindings import (
    AgentKnowledgeBaseBinding,
    bind_agent_to_kb,
    list_agent_kb_bindings,
    resolve_agent_kb_ids,
    unbind_agent_from_kb,
)
from fleetent.intelligence.knowledge_base.connectors.confluence import (
    ConfluenceConnectorConfig,
    ConfluenceSyncPlan,
    ConfluenceSyncSummary,
    plan_confluence_sync,
    sync_confluence,
)
from fleetent.intelligence.knowledge_base.connectors.google_drive import (
    GoogleDriveConnectorConfig,
    GoogleDriveSyncPlan,
    GoogleDriveSyncSummary,
    plan_google_drive_sync,
    sync_google_drive,
)
from fleetent.intelligence.knowledge_base.models import KnowledgeChunk, KnowledgeDocument
from fleetent.intelligence.knowledge_base.parsers import (
    ParsedDocument,
    ParsedSection,
    parse_html,
    parse_markdown,
    parse_text,
)
from fleetent.intelligence.knowledge_base.runtime import (
    archive,
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
    "ConfluenceConnectorConfig",
    "ConfluenceSyncPlan",
    "ConfluenceSyncSummary",
    "AgentKnowledgeBaseBinding",
    "GoogleDriveConnectorConfig",
    "GoogleDriveSyncPlan",
    "GoogleDriveSyncSummary",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "ParsedDocument",
    "ParsedSection",
    "SyncAction",
    "SyncExecutionSummary",
    "SyncPlan",
    "SyncPlanItem",
    "SyncPlanSummary",
    "archive",
    "bind_agent_to_kb",
    "delete",
    "execute_sync_plan",
    "ingest_parsed",
    "ingest_text",
    "iter_indexable_knowledge_chunks",
    "list_agent_kb_bindings",
    "parse_html",
    "parse_markdown",
    "parse_text",
    "plan_confluence_sync",
    "plan_google_drive_sync",
    "plan_local_directory_sync",
    "resolve_agent_kb_ids",
    "search",
    "sync_confluence",
    "sync_google_drive",
    "unbind_agent_from_kb",
]
