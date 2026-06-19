## Context

The latest `origin/main` already contains deterministic coverage for memory extraction fixtures and
KB management-plane seams. Production-like validation found that these tests do not cover the host
surface an operator uses:

- `kb_admin_api.py` has injectable placeholder functions such as `kb_ingest_text()` and
  `kb_search()` that return `wired: false` / empty lists by default. The server includes this router
  as-is, so production HTTP calls can appear successful without using the KB runtime.
- `tests/conftest.py` sets `ANTHROPIC_API_KEY=test-key` for every pytest run. This is correct for
  deterministic tests that only need `Settings()` initialization, but it conflicts with an explicit
  real-provider evaluation run after the operator has validated the real key with curl.
- `memory.extraction.strip_markdown_fence()` only strips a fence when the response starts with
  ``````, so real responses with a short preamble before fenced JSON are ignored entirely.

## Goals / Non-Goals

**Goals:**

- Make the local server `/admin/kb` route prove real KB ingest/search/delete behavior with migrated
  SQLite and vector-store test doubles.
- Let opt-in real LLM memory evaluation use real provider credentials without custom temp route
  files.
- Make memory extraction robust to common real LLM JSON wrapping and stable enough for the existing
  real-fixture acceptance cases.
- Keep deterministic unit/integration/evaluation tests as the default PR-safe path.
- Fix the intelligence validation manual so operators run commands that exist.

**Non-Goals:**

- Do not make real LLM, embedding, rerank, Google Drive, or Confluence tests default CI gates.
- Do not introduce LangChain / LlamaIndex or a separate KB service boundary.
- Do not implement a new ORM or bypass the unified DB runtime/store boundary.
- Do not add a web UI for review, scheduler, connector setup, or validation reporting.

## Decisions

### D1 - KB admin remains management-plane orchestration

`platform.knowledge_base_management.kb_admin_api` SHALL keep small seam functions for tests, but the
default seam implementations SHALL call public KB runtime APIs instead of placeholders. The router
may adapt request/response shapes, enforce auth/audit/confirmation, and format admin summaries; it
must not duplicate parsing, chunking, indexing, retrieval ranking, or deletion logic.

If current public KB APIs do not expose enough read models for list/documents/chunks, add narrow
public helpers in `fleetent.intelligence.knowledge_base` and cover them there. The admin API must
not import `KnowledgeStore` or runtime internals directly.

### D2 - HTTP production validation must detect placeholder behavior

Add an integration test that includes the real `/admin/kb` router without monkeypatching engine
seams, applies Alembic migrations to a temp DB, mocks only external vector calls, and proves:

- create KB returns 200 and list reflects the created KB,
- document import returns a non-null `document_id` and `chunks > 0`,
- document list and chunk preview show the imported document/chunks,
- `/admin/kb/search` returns the imported content through real KB search,
- delete removes the document from subsequent retrieval.

This test is the guard against another server build returning placeholder success.

### D3 - Real LLM eval opt-in preserves real credentials

Default tests still need `ANTHROPIC_API_KEY=test-key`. The opt-in real LLM path must distinguish
"test-only default key" from "operator supplied real key". Acceptable implementations:

- preserve an existing non-empty `ANTHROPIC_API_KEY` when `FLEETENT_EVAL_REAL_LLM=1`, or
- add an evaluation-only env indirection such as `FLEETENT_EVAL_REAL_LLM_KEY_ENV`, used by the real
  runner to populate the provider route without modifying production route semantics.

The chosen path must be documented and tested so `FLEETENT_EVAL_REAL_LLM=1 uv run pytest
tests/evaluation/test_memory_extraction_eval.py` either runs with a valid real key or skips with an
actionable missing-credential reason.

### D4 - Extraction parses JSON arrays from real-provider wrappers

Add an internal extraction helper that finds the first valid JSON array in:

- raw JSON array,
- fenced JSON with optional language tag,
- prose before/after a fenced JSON array,
- prose before/after an inline JSON array.

If no valid array is found, keep the current fail-closed behavior: return without mutating memory.
The helper must not execute code or accept arbitrary object roots.

### D5 - Normalize memory action content at the mutation boundary

Real models may return "Backend engineer" or "Prefers concise answers..." for facts whose contract
expects user-scoped third-person content. Normalize only low-risk, type-aware prefixes before
writing:

- `identity`: ensure stable user identity facts are represented as `User is ...` when the model
  returns a bare noun phrase or first-person variant.
- `preferences`: ensure durable preference facts are represented as `User prefers ...` when the
  model returns a bare "Prefers ..." variant.
- `context`: preserve concrete project/status content but remove obvious first-person framing when
  needed for fixture comparability.

Do not normalize deletes, target ids, memory types, or unsupported actions. Invalid or ambiguous
content remains ignored rather than guessed.

### D6 - Docs are verified like entrypoints

Update `docs/deployment/intelligence-roadmap-test-manual.md` to use
`fleetent admin memory shared ...` and to describe the real LLM validation env behavior. Extend the
existing deployment docs test so stale CLI names fail fast.

## Risks / Trade-offs

- **Sync wrappers around async KB APIs**: FastAPI route functions are currently sync. Implementation
  can convert affected handlers to `async def` or use a safe async bridge. Prefer `async def` route
  handlers for KB engine calls.
- **Real model variability**: deterministic tests should cover parser/normalizer behavior; real LLM
  fixtures remain opt-in and may still fail on quality. The readiness bar is that a valid provider
  call reaches the model and common valid JSON wrapping is handled.
- **Admin API response shape drift**: keep current response keys (`document_id`, `chunks`, `results`)
  and add fields rather than breaking callers where possible.
- **Another session on deployment roadmap**: this change does not touch deployment/observability
  code paths except docs references in the intelligence manual, reducing overlap.

## Verification Strategy

- TDD red/green per task with scoped tests first.
- Run selected intelligence validation tests after implementation:
  - `uv run pytest tests/integration/test_kb_admin_api.py -x -q`
  - `uv run pytest tests/unit/test_memory_extraction.py tests/evaluation/test_memory_extraction_eval.py -x -q`
  - `uv run pytest tests/integration/test_deployment_docs.py -x -q`
- Run final project gate:
  - `uv run pytest -x -q`
  - `uv run ruff format src tests`
  - `uv run ruff check src tests`
  - `uv run mypy src`
  - `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`
  - `openspec validate intelligence-production-validation-readiness --strict`
- Manual real-provider smoke remains opt-in and records evidence without secrets.
