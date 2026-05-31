## Why

Vector-only search is enough for the first KB loop, but enterprise documents need exact-term retrieval
for product IDs, names, error codes and Chinese/English mixed phrases. `knowledge-bridge` already
validated BM25 + vector + RRF as a useful direction, but fleetent must implement it with SQLite FTS5 and
existing vector_store boundaries.

This change adds hybrid retrieval after `knowledge-base-core`, without introducing reranker, query planner
or external search services.

## What Changes

- Add SQLite FTS5 indexing for `knowledge_chunks` content.
- Add `search_mode` or equivalent option for `search()`:
  - `vector`
  - `keyword`
  - `hybrid`
- Implement keyword search via SQLite FTS5 / BM25 within tenant + kb scope.
- Implement RRF fusion of vector and keyword candidates.
- Keep result shape as `KnowledgeChunk`.
- Preserve namespace and tenant isolation.
- Add basic lexical normalization for Chinese/English mixed content sufficient for tests.

## Out of Scope

- No OpenSearch / Elasticsearch.
- No rerank provider integration.
- No query planner / translator.
- No graph search.
- No external tokenizer service.

## Dependencies

- Requires `knowledge-base-core`.
- Can run in parallel with `knowledge-base-parsers-basic` after core if write conflicts are coordinated.

## Impact

- **Code**: adds retrieval module or extends search implementation.
- **Database**: adds Alembic migration for FTS table/index owned by knowledge-base.
- **Tests**: integration tests for vector-only, keyword-only and hybrid search.
