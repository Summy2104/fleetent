## Why

Memory extraction and KB retrieval already have deterministic evaluation baselines, and KB retrieval
has a real embedding smoke guard. What is still missing is one evaluation contract that exercises
both memory semantic retrieval and KB retrieval through the same embedding/vector-store path. Without
that, embedding provider or vector backend changes can improve one path while silently regressing the
other.

This change adds a combined memory + KB embedding evaluation. The default path remains deterministic
and isolated. Real HTTP embedding evaluation is manual opt-in only, skips when credentials are
missing, and must never run in default PR/main gates.

## What Changes

- Add `tests/evaluation/` fixtures for memory semantic retrieval and KB retrieval in one suite.
- Add a combined embedding evaluation runner that:
  - creates tmp SQLite databases for fleetent data and vector store
  - inserts memory records through the memory store boundary or current public behavior
  - ingests KB documents through knowledge-base public API
  - configures vector store with deterministic embedding by default
  - reindexes memory and KB via `vector_store.reindex()`
  - validates expected/forbidden memory snippets and KB snippets in top-k retrieval
- Add an optional real HTTP embedding runner behind explicit env vars.
- Keep all default tests isolated from real LLM, real embedding services, real SaaS, and `data/`.
- Update capability docs and CI quality-gate language.

## Out of Scope

- No new embedding provider, model hosting, sidecar runtime, or deployment choice.
- No reranker evaluation or rerank integration into KB search.
- No LLM-graded answer quality.
- No Shared Memory.
- No production configuration default changes.
- No persistent job history, scheduler, dashboard, or admin UI.
- No Confluence / Google Drive connector behavior.

## Dependencies

- Requires `memory-sqlite-semantic-store`, `knowledge-base-retrieval-evaluation`,
  `embedding-rerank-provider-abstraction`, `vector-store-sqlite-backend`, and
  `vector-store-reindex-jobs`.
- Uses the existing HTTP embedding provider contract for manual real-provider smoke.

## Module Boundary Impact

- **Owning package**: no production owning package; this change belongs to memory/KB/vector-store
  evaluation test ownership under `tests/evaluation`.
- **Public API surface**: no new production API. The runner uses existing
  `memory_layer.search()`, `knowledge_base.ingest_text()`, `knowledge_base.search()`,
  `vector_store.reindex()`, `ReindexRequest`, and vector runtime configuration.
- **Owned tables**: none. Tests use existing `memory_items`, `knowledge_*`, and `vector_items`
  tables in tmp SQLite databases.
- **Config namespace**: no production config. Optional real HTTP embedding smoke uses explicit
  `FLEETENT_EVAL_*` environment variables.
- **Cross-module dependencies**: evaluation uses memory-layer, knowledge-base, and vector-store
  public APIs. It does not import internal store implementations except where existing tests already
  configure runtime settings for isolated tmp databases.
- **Migration / shim plan**: none.

## Impact

- **Code**: evaluation helper and tests only unless fixtures reveal an existing public contract bug.
- **Tests**: adds deterministic combined retrieval evaluation and real embedding skip/opt-in coverage.
- **CI**: no default PR/main gate change; evaluation remains manual.
- **Data**: no real user data and no writes under `data/`.
