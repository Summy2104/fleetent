## Why

Current local directory sync scans supported files and mutates the knowledge base in one pass. It can skip
unchanged files through `knowledge_source_states`, but it does not expose a deterministic sync plan, cannot
represent source-side deletes, and gives future connectors no shared contract for planning versus execution.

This change introduces a sync planner boundary so local directory sync and later Confluence / Google Drive
connectors can share the same action model without introducing background jobs or third-party connector scope
too early.

## What Changes

- Add sync planning dataclasses and action names for knowledge-base sources.
- Add `plan_local_directory_sync()` and `execute_sync_plan()` public APIs.
- Add a local directory planner that compares listed source documents with `knowledge_source_states`.
- Represent new, changed, unchanged, unsupported, and missing-source documents as explicit plan items.
- Add plan execution that applies supported actions idempotently and updates source state only after successful
  execution.
- Refactor `sync_local_directory()` to run `plan + execute` while preserving the existing public entry point.
- Delete KB documents whose previously synced local source path is missing from the current source listing.
- Update knowledge-base docs and roadmap status.

## Out of Scope

- No Confluence, Google Drive, Slack file, S3, SharePoint, or other remote connector.
- No scheduler, queue, worker, admin API, dashboard, or runtime dynamic job management.
- No sync run / sync item persistence table.
- No source ACL mapping, OAuth, token refresh, webhook handling, or incremental remote API cursor.
- No PDF / Office parsing, graph extraction, rerank, query planner, or vector reindex behavior.

## Module Boundary Impact

- **Owning package**: `intelligence.knowledge_base`.
- **Public API surface**: `SyncAction`, `SyncPlan`, `SyncPlanItem`, `SyncPlanSummary`,
  `SyncExecutionSummary`, `plan_local_directory_sync()`, and `execute_sync_plan()`.
- **Owned tables**: no new tables; continues to use `knowledge_source_states`.
- **Config namespace**: none.
- **Cross-module dependencies**: depends on knowledge-base parser/runtime public APIs and vector_store through
  existing ingest/delete paths only.
- **Migration / shim plan**: no import migration; `sync_local_directory()` remains the stable public entry point
  and delegates to the new planner/executor internally.
