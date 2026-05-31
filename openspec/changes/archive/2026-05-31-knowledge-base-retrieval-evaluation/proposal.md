## Why

Knowledge-base search quality should not be validated only through unit tests. We need deterministic
evaluation fixtures that measure whether ingest/chunking/retrieval returns expected chunks, starting with
vector-only core behavior and extending to hybrid search when available.

This change creates an evaluation layer for KB retrieval without making it a PR gate or requiring real
embedding models by default.

## What Changes

- Add `tests/evaluation` fixtures for small enterprise-style documents.
- Add KB retrieval evaluation runner that:
  - creates tmp database
  - ingests fixture documents
  - runs queries
  - asserts expected chunk ids or content snippets are returned
  - asserts forbidden chunks are not returned
- Default evaluation uses deterministic embedding and does not call external services.
- Optional real embedding evaluation is explicitly gated by env vars.
- Update CI quality gate docs/spec so KB evaluation is manually runnable but not part of default PR gate.

## Out of Scope

- No production ranking metrics dashboard.
- No real model benchmark as default CI.
- No reranker evaluation.
- No query planner evaluation.

## Dependencies

- Requires `knowledge-base-core`.
- Can initially evaluate vector-only retrieval.
- After `knowledge-base-hybrid-search`, fixtures may be extended to cover keyword/hybrid modes.

## Impact

- **Code**: test/evaluation helper only.
- **Database**: no persistent schema changes.
- **Tests**: adds manual evaluation tests, default deterministic and isolated from `data/`.
