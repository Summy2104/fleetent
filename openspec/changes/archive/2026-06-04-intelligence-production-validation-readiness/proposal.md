## Why

Production-like validation of `docs/capabilities/roadmaps/intelligence-roadmap.md` on the
latest `origin/main` exposed two Pilot blockers and one documentation gap:

- `/admin/kb` is mounted on the server, but its default engine seams still return placeholders.
  Creating a KB, importing a document, listing documents, and searching over HTTP can all return
  200 while no real KB document is stored or retrieved.
- `FLEETENT_EVAL_REAL_LLM=1` memory extraction evaluation is opt-in, but the global pytest
  fixture overwrites `ANTHROPIC_API_KEY` with `test-key`, so a real provider run cannot use the
  operator's validated key without an out-of-band route override.
- The real Anthropic route can answer successfully, but `extract_and_update()` currently drops
  useful model output when the JSON array is wrapped in prose or a fenced block after a preamble;
  some fixtures also fail because real model content is not normalized tightly enough for the
  memory contract.
- The manual intelligence validation guide still documents `fleetent admin shared-memory ...`,
  while the current CLI entrypoint is `fleetent admin memory shared ...`.

The current deterministic tests remain valuable, but they do not prove the production surface that
an operator actually validates: local server, migrated SQLite database, real provider route, and
HTTP/CLI entrypoints.

## What Changes

- Wire `/admin/kb` default seams to the `fleetent.intelligence.knowledge_base` public API so local
  server HTTP validation can create KBs, ingest text/markdown/html payloads, list documents/chunks,
  delete documents, and search real indexed content without monkeypatching.
- Harden memory extraction parsing and action normalization so real LLM responses that include
  prose plus fenced JSON, or equivalent first-person/third-person content variants, still produce
  the intended memory mutations.
- Make opt-in real LLM evaluation preserve the operator's real credential path instead of being
  forced to `ANTHROPIC_API_KEY=test-key` by default test setup.
- Update intelligence validation docs and docs tests so the shared memory CLI commands match the
  current `fleetent admin memory shared ...` command tree and the production validation steps
  describe the real LLM credential behavior.

## Capabilities

### Modified Capabilities

- `kb-admin-api`: host `/admin/kb` SHALL use the real knowledge-base engine by default for the
  production validation path, while keeping seams mockable for management-layer tests.
- `knowledge-base`: the public KB runtime remains the owner of parsing, chunking, indexing,
  retrieval, and deletion; the admin plane only orchestrates it.
- `memory-layer`: real LLM evaluation SHALL be runnable with explicit operator opt-in and valid
  provider credentials, and extraction SHALL tolerate common real-provider JSON wrapping.
- `ci-quality-gate`: default deterministic tests SHALL continue using test-only credentials, while
  opt-in real-provider evaluation SHALL not be clobbered by default env fixtures.
- `capability-roadmaps`: the intelligence production validation manual SHALL match current CLI
  entrypoints and document the real-provider validation workflow accurately.

## Impact

- **owning packages**:
  - `platform.knowledge_base_management` owns the `/admin/kb` HTTP management behavior.
  - `intelligence.knowledge_base` owns KB ingest/search/delete runtime behavior.
  - `intelligence.memory` owns extraction parsing and memory mutation behavior.
  - `tests/evaluation` owns opt-in real-provider evaluation harness behavior.
- **public API surface**:
  - No new cross-module public API is expected.
  - `/admin/kb` SHALL call existing public exports from `fleetent.intelligence.knowledge_base`
    (`ingest_text`, `search`, `delete`, and, if needed, public store-backed listing helpers added
    as public exports rather than internal imports).
  - Any helper added for parsing model JSON output SHALL remain internal to `intelligence.memory`
    unless a reusable public contract is explicitly needed.
- **owned tables**: no new tables. The change updates the existing `knowledge_bases` table with
  metadata needed by the admin contract (`description`, `archived_at`) and keeps using existing
  `knowledge_documents`, `knowledge_chunks`, vector index state, audit log, and `memory_items`.
- **config namespace**: no new production config namespace expected. Tests MAY add an opt-in
  evaluation-only env such as `FLEETENT_EVAL_REAL_LLM_KEY_ENV` or preserve an existing real key when
  `FLEETENT_EVAL_REAL_LLM=1`; this must not affect normal runtime config.
- **cross-module dependencies**:
  - `platform.knowledge_base_management` may depend on `fleetent.intelligence.knowledge_base`
    public API only.
  - It must not import `intelligence.knowledge_base.runtime`, `store`, or connector internals.
  - `tests/evaluation` may import app public APIs and monkeypatch injection seams.
- **migration / shim plan**: add an Alembic migration for `knowledge_bases` metadata if the
  implementation needs persisted description/archive state. This change does not move modules or
  remove import paths.

## Out Of Scope

- New KB admin UI work.
- New provider types, embedding providers, rerank providers, or connector implementations.
- Real Google Drive / Confluence credential provisioning.
- Full production deployment hardening already covered by the parallel observability deployment
  roadmap validation.
