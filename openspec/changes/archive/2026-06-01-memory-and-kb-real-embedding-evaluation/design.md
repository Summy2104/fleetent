## Context

Memory semantic search and KB retrieval both depend on vector-store embeddings. Existing evaluations
test memory extraction state and KB retrieval separately. This spec adds an end-to-end retrieval
evaluation that proves the shared embedding/vector path can serve both owners from isolated source
records.

The default runner uses deterministic embeddings so it remains stable, fast, and offline. The real
embedding runner is only a smoke path for manually testing a configured HTTP embedding service.

## Fixture Format

Each fixture is a JSON object with:

- `name`: stable case identifier.
- `user_id`: memory user scope.
- `tenant_id`, `kb_id`: KB scope.
- `memories`: records with `id`, `type`, `content`, and optional timestamps/expiry.
- `documents`: KB documents with `filename`, `content`, and optional source metadata.
- `queries`: assertions with:
  - `owner`: `memory` or `knowledge_base`
  - `text`
  - `top_k`
  - `expected`: snippets that must appear in retrieved memory or KB chunks
  - `forbidden`: snippets that must not appear

The runner fails fast on missing required fields, unsupported owners, empty query text, or invalid
top-k values.

## Runner

The deterministic runner:

1. Creates tmp fleetent SQLite and tmp vector SQLite database paths.
2. Applies migrations to the fleetent database.
3. Configures knowledge-base and vector-store runtimes with deterministic embedding.
4. Inserts memory records into `memory_items` through the same schema contract used by
   `memory_layer.search()`.
5. Ingests KB documents through `knowledge_base.ingest_text()`.
6. Calls `vector_store.reindex(ReindexRequest(owner="memory", user_id=...))`.
7. Calls `vector_store.reindex(ReindexRequest(owner="knowledge_base", tenant_id=..., kb_id=...))`.
8. Runs memory queries through `memory_layer.search()` and KB queries through `knowledge_base.search()`.
9. Validates expected and forbidden snippets.

The runner records reindex summaries so tests can prove both owners were rebuilt through the public
reindex API.

## Optional Real Embedding Runner

The real runner is guarded by `FLEETENT_EVAL_REAL_EMBEDDING=1` and requires endpoint, model, API key,
and dimensions:

- `FLEETENT_EVAL_EMBEDDING_ENDPOINT`
- `FLEETENT_EVAL_EMBEDDING_MODEL`
- `FLEETENT_EVAL_EMBEDDING_API_KEY`
- `FLEETENT_EVAL_EMBEDDING_DIMENSIONS`

If any required value is absent, the test skips. It still uses tmp fleetent/vector databases and
synthetic fixtures. It does not use real memory, real KB documents, or external SaaS.

## Error Handling

Invalid fixtures raise a dedicated validation error. Retrieval assertion failures name the missing
or forbidden snippet and owner. Real-provider errors are surfaced only when the user explicitly opts
in and credentials/config are present.

## Testing

Tests follow the project TDD gate:

- Fixture schema tests fail before loader implementation.
- Deterministic runner tests fail before tmp database/runtime setup exists.
- Reindex tests fail before both memory and KB owners are rebuilt.
- Retrieval expectation tests fail before memory and KB queries are validated.
- Real embedding skip tests fail before opt-in guard implementation.

The loop command is `uv run pytest tests/evaluation/test_memory_kb_embedding_eval.py -x -q`.
