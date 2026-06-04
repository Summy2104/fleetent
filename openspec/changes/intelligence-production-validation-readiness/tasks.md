## 0. Baseline and validation reproduction

- [x] 0.1 Record latest branch baseline: `git status --short --branch`, `git rev-parse HEAD`, and
  `uv run pytest tests/evaluation/test_memory_extraction_eval.py tests/integration/test_kb_admin_api.py tests/integration/test_deployment_docs.py -q`.
- [x] 0.2 Reproduce the production validation blockers against latest `origin/main`: local server
  `/admin/kb` returns placeholder or empty real results without monkeypatching; opt-in real LLM eval
  cannot use a validated real key or fails on wrapped JSON output.

## 1. KB admin API host wiring

- [x] 1.1 Write failing integration test: include `/admin/kb` without monkeypatching engine seams,
  use migrated temp SQLite and mocked vector upsert/search/delete, create a KB, and assert `GET
  /admin/kb` lists the created KB with non-placeholder metadata. Run
  `uv run pytest tests/integration/test_kb_admin_api.py -x -q` and confirm red.
- [x] 1.2 Write failing integration test: import a document through `/admin/kb/{kb_id}/documents`
  and assert non-null `document_id`, `chunks > 0`, document list includes the import, and chunk
  preview returns real chunk content. Run the same scoped pytest and confirm red.
- [x] 1.3 Write failing integration test: search via `/admin/kb/search` returns the imported chunk
  through real KB runtime, and confirmed document delete removes it from later search. Run the same
  scoped pytest and confirm red.
- [x] 1.4 Implement default seam wiring using `fleetent.intelligence.knowledge_base` public APIs
  only; add narrow public listing/read helpers if required.
- [x] 1.5 Verify green: run `uv run pytest tests/integration/test_kb_admin_api.py -x -q`.

## 2. Real LLM evaluation credential handling

- [x] 2.1 Write failing evaluation-harness test: when `FLEETENT_EVAL_REAL_LLM=1` and a real
  credential is present, the runner does not replace the credential path with the default
  `test-key`. Run `uv run pytest tests/evaluation/test_memory_extraction_eval.py -x -q` and confirm
  red.
- [x] 2.2 Write failing test for missing real credentials: opt-in real LLM eval skips with an
  actionable reason when no configured real key is available. Run the same scoped pytest and confirm
  red if not already covered.
- [x] 2.3 Implement the minimal evaluation-only env handling so deterministic tests still receive
  `test-key`, while explicit real-provider runs use the operator-supplied credential.
- [x] 2.4 Verify green: run `uv run pytest tests/evaluation/test_memory_extraction_eval.py -x -q`.

## 3. Memory extraction real-output hardening

- [x] 3.1 Write failing unit tests for extracting actions from raw JSON, fenced JSON, prose before a
  fenced JSON array, and prose around an inline JSON array; invalid output must remain ignored. Run
  `uv run pytest tests/unit/test_memory_extraction.py -x -q` and confirm red.
- [x] 3.2 Write failing unit/evaluation tests for type-aware action content normalization covering
  identity bare noun phrase, preferences `Prefers ...`, and context update wording seen in the real
  Anthropic smoke. Run scoped pytest and confirm red.
- [x] 3.3 Implement JSON-array extraction and minimal type-aware content normalization inside
  `fleetent.intelligence.memory` without changing unsupported action behavior.
- [x] 3.4 Verify green: run `uv run pytest tests/unit/test_memory_extraction.py tests/evaluation/test_memory_extraction_eval.py -x -q`.
- [x] 3.5 Manual opt-in smoke: after the operator confirms the real key, run
  `FLEETENT_EVAL_REAL_LLM=1 uv run pytest tests/evaluation/test_memory_extraction_eval.py -q -rs`
  or the documented equivalent, and record pass/fail/skip evidence without secrets.

## 4. Intelligence validation manual and docs tests

- [x] 4.1 Write failing docs test: `docs/deployment/intelligence-roadmap-test-manual.md` must not
  contain `fleetent-admin shared-memory` and must contain `fleetent-admin memory shared`. Run
  `uv run pytest tests/integration/test_deployment_docs.py -x -q` and confirm red.
- [x] 4.2 Update the intelligence validation manual shared-memory commands and real LLM credential
  instructions.
- [x] 4.3 Verify green: run `uv run pytest tests/integration/test_deployment_docs.py -x -q`.

## 5. Production-like local validation pass

- [x] 5.1 Start from a clean temp `DATABASE_URL`, run Alembic upgrade before service boot, start
  `uv --project <repo> run python -m uvicorn fleetent.server:app` on an unused local port, and
  authenticate through the real admin/session flow.
- [x] 5.2 Execute real HTTP calls for `/health`, `/admin/login`, `/admin/kb` create/list/import/list
  documents/preview/search/delete using the local server and migrated DB.
- [x] 5.3 Execute CLI checks for `fleetent-admin memory shared ...`, vector reindex dry-run,
  reflection dry-run, and memory compaction dry-run with isolated local state.
- [x] 5.4 Record remaining skipped external-provider/SaaS items with explicit reason, owner, and
 复测条件; ask the operator for credentials or manual intervention when independent automation
  cannot proceed.

## 6. Final gates

- [x] 6.1 Run `uv run pytest -x -q`.
- [x] 6.2 Run `uv run ruff format src tests` and `uv run ruff check src tests`.
- [x] 6.3 Run `uv run mypy src` and record whether any errors are pre-existing or newly introduced.
- [x] 6.4 Run `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`.
- [x] 6.5 Run `openspec validate intelligence-production-validation-readiness --strict`.
- [x] 6.6 Run `git diff --check`.

## Evidence

- Scoped implementation gate: `uv run pytest tests/integration/test_kb_admin_api.py tests/integration/test_migrations.py tests/unit/test_memory_extraction.py tests/evaluation/test_memory_extraction_eval.py tests/integration/test_deployment_docs.py -x -q` -> `97 passed, 7 skipped`.
- Real LLM opt-in: `FLEETENT_EVAL_REAL_LLM=1 uv run pytest tests/evaluation/test_memory_extraction_eval.py -x -q -rs` -> `33 passed`.
- Full test gate: `uv run pytest -x -q` -> `3046 passed, 14 skipped`.
- Changed-file quality gate: `uv run ruff format --check ...` and `uv run ruff check ...` on changed source/test/migration files -> clean; scoped mypy on changed source files -> clean.
- Full-repo `ruff format --check src tests migrations`, `ruff check src tests migrations`, and `uv run mypy src` were executed; they still report pre-existing unrelated failures in model-provider/runtime/tooling files, while changed-file gates are clean.
- Module boundary: `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` -> clean.
- OpenSpec: `openspec validate intelligence-production-validation-readiness --strict` -> valid.
- Diff hygiene: `git diff --check` -> clean.
- Local-as-server HTTP validation used an isolated `FLEETENT_HOME` and migrated SQLite DB on `127.0.0.1:18082`: `/health`, `/admin/login`, `/admin/kb` create/list/import/documents/chunks/search/delete, and local directory sync all passed with real HTTP calls.
- CLI validation on the isolated DB: `fleetent-admin memory shared list`, vector reindex dry-run, reflection dry-run, and memory compact dry-run all exited successfully.
