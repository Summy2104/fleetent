## Why

Memory and knowledge-base store their source text in SQLite, while vector_store holds derived embeddings. When
the embedding provider, embedding model, vector backend, or vector data is changed, operators need a safe way
to rebuild vector indexes from the source of truth without re-ingesting documents or re-extracting memories.

This change adds a synchronous reindex boundary that can rebuild memory and knowledge-base vector namespaces
through public module APIs. It intentionally stops short of a background job platform.

## What Changes

- Add `vector_store.clear_namespace(namespace)` so rebuild can remove stale vectors before upserting current
  source records.
- Add reindex dataclasses and `reindex(ReindexRequest) -> ReindexSummary`.
- Support `dry_run` and `rebuild` mode for memory and knowledge-base owners.
- Add a shared `IndexableItem` shape for source records that can be written to vector_store.
- Add memory public API `iter_indexable_memories(user_id)` for a user.
- Add knowledge-base public API `iter_indexable_knowledge_chunks(tenant_id, kb_id)` for a tenant/kb.
- Reindex only consumes memory / knowledge-base / vector_store public APIs; it does not direct-SQL into
  module-owned tables.
- Update vector-store, memory, knowledge-base, and roadmap docs.

## Out of Scope

- No persistent `reindex_jobs` table, job history, retry queue, worker, scheduler, admin API, dashboard, or
  dynamic runtime job management.
- No Confluence / Google Drive connector behavior.
- No real embedding or rerank evaluation.
- No sqlite-vec, Qdrant, OpenSearch, Elasticsearch, or backend migration adapter.
- No chunking changes, memory extraction changes, or source sync behavior.
- No automatic reindex trigger on config changes.

## Module Boundary Impact

- **Owning package**: `intelligence.vector_store`.
- **Public API surface**: `clear_namespace()`, `IndexableItem`, `ReindexRequest`, `ReindexSummary`,
  `reindex()`, `memory_layer.iter_indexable_memories()`, and
  `knowledge_base.iter_indexable_knowledge_chunks()`.
- **Owned tables**: no new tables; vector_store continues to own `vector_items` in SQLite backend.
- **Config namespace**: none.
- **Cross-module dependencies**: vector_store reindex depends on memory-layer and knowledge-base public
  indexable iterator APIs, and writes via vector_store public API only.
- **Migration / shim plan**: additive public APIs; no import migration.
