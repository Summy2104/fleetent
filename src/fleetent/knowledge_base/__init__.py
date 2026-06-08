"""Compatibility-focused top-level API for knowledge-base features.

Historically, callers imported knowledge-base symbols from
``fleetent.knowledge_base`` directly. Keep that contract stable while the
implementation is split into focused subpackages.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module

from .bindings import (
    AgentKnowledgeBaseBinding,
    bind_agent_to_kb,
    list_agent_kb_bindings,
    resolve_agent_kb_ids,
    unbind_agent_from_kb,
)
from .config import (
    KnowledgeBaseConfig,
    KnowledgeConfigSnapshot,
    KnowledgeIndexingConfig,
    KnowledgeSourceConfig,
    KnowledgeSyncConfig,
    knowledge_config_path,
    load_knowledge_config,
)
from .connectors.confluence import (
    ConfluenceConnectorConfig,
    ConfluenceSyncPlan,
    ConfluenceSyncSummary,
    plan_confluence_sync,
    sync_confluence,
)
from .connectors.google_drive import (
    GoogleDriveConnectorConfig,
    GoogleDriveSyncPlan,
    GoogleDriveSyncSummary,
    plan_google_drive_sync,
    sync_google_drive,
)
from .connectors.sync import LocalDirectorySourceConfig
from .core.contracts import (
    KnowledgeDocument,
    KnowledgeReadable,
    KnowledgeWritable,
)
from .core.models import KnowledgeChunk
from .extraction import ExtractedEntity, ExtractedRelation, ExtractionResult, run_entity_extraction
from .extraction_store import KnowledgeEntity, KnowledgeExtractionRun
from .operations import (
    ConnectorCheckResult,
    ConnectorDefinition,
    ConnectorStatus,
    ConnectorSummary,
    ConnectorSyncResult,
    check_connector,
    get_connector_config,
    get_connector_status,
    list_configured_connectors,
    run_connector_sync,
)
from .parsers import (
    ParsedDocument,
    ParsedSection,
    parse_document,
    parse_docx,
    parse_html,
    parse_markdown,
    parse_pdf,
    parse_pptx,
    parse_text,
    parse_xlsx,
)
from .planner import (
    KnowledgeSearchOptions,
    KnowledgeSearchPlan,
    KnowledgeSearchStep,
    execute_knowledge_search_plan,
    plan_knowledge_search,
)
from .retrieval import SearchMode
from .runtime import (
    archive,
    archive_knowledge_base,
    create_knowledge_base,
    delete,
    delete_document,
    ingest_parsed,
    ingest_text,
    is_active_knowledge_base,
    iter_indexable_knowledge_chunks,
    list_documents,
    list_knowledge_bases,
    preview_document_chunks,
    search,
    update_knowledge_base_description,
)
from .sync_planner import (
    SyncAction,
    SyncExecutionSummary,
    SyncPlan,
    SyncPlanItem,
    SyncPlanSummary,
    execute_sync_plan,
    plan_local_directory_sync,
)

_REEXPORTS = {
    "core": "fleetent.knowledge_base.core",
    "ingest": "fleetent.knowledge_base.ingest",
    "management": "fleetent.knowledge_base.management",
    "retrieval": "fleetent.knowledge_base.retrieval",
    "connectors": "fleetent.knowledge_base.connectors",
    "parsers": "fleetent.knowledge_base.parsers",
    "runtime": "fleetent.knowledge_base.runtime",
    "operations": "fleetent.knowledge_base.operations",
    "planner": "fleetent.knowledge_base.planner",
    "sync_planner": "fleetent.knowledge_base.sync_planner",
    "bindings": "fleetent.knowledge_base.bindings",
    "config": "fleetent.knowledge_base.config",
    "extraction": "fleetent.knowledge_base.extraction",
    "extraction_store": "fleetent.knowledge_base.extraction_store",
    "store": "fleetent.knowledge_base.store",
}


_ATTRIBUTE_EXPORTS: dict[str, Callable[[], object]] = {
    "KnowledgeChunk": lambda: KnowledgeChunk,
    "KnowledgeDocument": lambda: KnowledgeDocument,
    "KnowledgeReadable": lambda: KnowledgeReadable,
    "KnowledgeWritable": lambda: KnowledgeWritable,
    "KnowledgeBaseConfig": lambda: KnowledgeBaseConfig,
    "KnowledgeConfigSnapshot": lambda: KnowledgeConfigSnapshot,
    "KnowledgeIndexingConfig": lambda: KnowledgeIndexingConfig,
    "KnowledgeSourceConfig": lambda: KnowledgeSourceConfig,
    "KnowledgeSyncConfig": lambda: KnowledgeSyncConfig,
    "KnowledgeEntity": lambda: KnowledgeEntity,
    "KnowledgeExtractionRun": lambda: KnowledgeExtractionRun,
    "ExtractedEntity": lambda: ExtractedEntity,
    "ExtractedRelation": lambda: ExtractedRelation,
    "ExtractionResult": lambda: ExtractionResult,
    "ParsedDocument": lambda: ParsedDocument,
    "ParsedSection": lambda: ParsedSection,
    "parse_document": lambda: parse_document,
    "parse_docx": lambda: parse_docx,
    "parse_html": lambda: parse_html,
    "parse_markdown": lambda: parse_markdown,
    "parse_pdf": lambda: parse_pdf,
    "parse_pptx": lambda: parse_pptx,
    "parse_text": lambda: parse_text,
    "parse_xlsx": lambda: parse_xlsx,
    "SearchMode": lambda: SearchMode,
    "SyncAction": lambda: SyncAction,
    "SyncExecutionSummary": lambda: SyncExecutionSummary,
    "SyncPlan": lambda: SyncPlan,
    "SyncPlanItem": lambda: SyncPlanItem,
    "SyncPlanSummary": lambda: SyncPlanSummary,
    "KnowledgeSearchOptions": lambda: KnowledgeSearchOptions,
    "KnowledgeSearchPlan": lambda: KnowledgeSearchPlan,
    "KnowledgeSearchStep": lambda: KnowledgeSearchStep,
    "ConfluenceConnectorConfig": lambda: ConfluenceConnectorConfig,
    "ConfluenceSyncPlan": lambda: ConfluenceSyncPlan,
    "ConfluenceSyncSummary": lambda: ConfluenceSyncSummary,
    "GoogleDriveConnectorConfig": lambda: GoogleDriveConnectorConfig,
    "GoogleDriveSyncPlan": lambda: GoogleDriveSyncPlan,
    "GoogleDriveSyncSummary": lambda: GoogleDriveSyncSummary,
    "LocalDirectorySourceConfig": lambda: LocalDirectorySourceConfig,
    "AgentKnowledgeBaseBinding": lambda: AgentKnowledgeBaseBinding,
    "ConnectorCheckResult": lambda: ConnectorCheckResult,
    "ConnectorDefinition": lambda: ConnectorDefinition,
    "ConnectorStatus": lambda: ConnectorStatus,
    "ConnectorSummary": lambda: ConnectorSummary,
    "ConnectorSyncResult": lambda: ConnectorSyncResult,
    "archive": lambda: archive,
    "archive_knowledge_base": lambda: archive_knowledge_base,
    "bind_agent_to_kb": lambda: bind_agent_to_kb,
    "check_connector": lambda: check_connector,
    "create_knowledge_base": lambda: create_knowledge_base,
    "delete": lambda: delete,
    "delete_document": lambda: delete_document,
    "execute_knowledge_search_plan": lambda: execute_knowledge_search_plan,
    "execute_sync_plan": lambda: execute_sync_plan,
    "get_connector_config": lambda: get_connector_config,
    "get_connector_status": lambda: get_connector_status,
    "ingest_parsed": lambda: ingest_parsed,
    "ingest_text": lambda: ingest_text,
    "iter_indexable_knowledge_chunks": lambda: iter_indexable_knowledge_chunks,
    "is_active_knowledge_base": lambda: is_active_knowledge_base,
    "knowledge_config_path": lambda: knowledge_config_path,
    "list_agent_kb_bindings": lambda: list_agent_kb_bindings,
    "list_configured_connectors": lambda: list_configured_connectors,
    "list_documents": lambda: list_documents,
    "list_knowledge_bases": lambda: list_knowledge_bases,
    "load_knowledge_config": lambda: load_knowledge_config,
    "plan_confluence_sync": lambda: plan_confluence_sync,
    "plan_google_drive_sync": lambda: plan_google_drive_sync,
    "plan_knowledge_search": lambda: plan_knowledge_search,
    "plan_local_directory_sync": lambda: plan_local_directory_sync,
    "preview_document_chunks": lambda: preview_document_chunks,
    "resolve_agent_kb_ids": lambda: resolve_agent_kb_ids,
    "run_connector_sync": lambda: run_connector_sync,
    "run_entity_extraction": lambda: run_entity_extraction,
    "search": lambda: search,
    "sync_confluence": lambda: sync_confluence,
    "sync_google_drive": lambda: sync_google_drive,
    "unbind_agent_from_kb": lambda: unbind_agent_from_kb,
    "update_knowledge_base_description": lambda: update_knowledge_base_description,
    "EntityRef": lambda: import_module("fleetent.knowledge_base.retrieval.graph_search").EntityRef,
    "RelationRef": lambda: (
        import_module("fleetent.knowledge_base.retrieval.graph_search").RelationRef
    ),
    "GraphSearchChunk": lambda: (
        import_module("fleetent.knowledge_base.retrieval.graph_search").GraphSearchChunk
    ),
    "GraphSearchResult": lambda: (
        import_module("fleetent.knowledge_base.retrieval.graph_search").GraphSearchResult
    ),
    "graph_search": lambda: (
        import_module("fleetent.knowledge_base.retrieval.graph_search").graph_search
    ),
}


def __getattr__(name: str) -> object:
    if name in _REEXPORTS:
        return import_module(_REEXPORTS[name])
    if name in _ATTRIBUTE_EXPORTS:
        return _ATTRIBUTE_EXPORTS[name]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted({*globals().keys(), *_REEXPORTS.keys(), *_ATTRIBUTE_EXPORTS.keys()})


__all__ = sorted(
    {
        *_REEXPORTS.keys(),
        *_ATTRIBUTE_EXPORTS.keys(),
    }
)
