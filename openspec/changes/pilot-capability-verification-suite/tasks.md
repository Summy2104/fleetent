## 0. Scope and inventory

- [ ] 0.1 Inventory existing tests for the 7 owner capability domains and map them to roadmap rows.
- [ ] 0.2 Identify missing high-value contract tests without duplicating existing coverage.
- [ ] 0.3 Confirm every new test uses tmp data, fake providers, fake connectors or explicit opt-in smoke flags.

## 1. Capability contract integration tests

- [ ] 1.1 Write failing tests: Observability contract evidence covers trace query, usage/performance summary and diagnostics redaction/export.
- [ ] 1.2 Implement: add or adjust only the minimal test fixtures/public helpers needed for Observability tests to pass.
- [ ] 1.3 Verify green: run `uv run pytest tests/integration -x -q`.

- [ ] 1.4 Write failing tests: Memory and Shared Memory contracts cover item lifecycle, retention/compaction, vector namespace and tenant/team isolation.
- [ ] 1.5 Implement: add or adjust only the minimal test fixtures/public helpers needed for Memory tests to pass.
- [ ] 1.6 Verify green: run `uv run pytest tests/integration -x -q`.

- [ ] 1.7 Write failing tests: Long-term Context contracts cover source attribution, deterministic budget decision and agent ownership-based Shared Memory policy.
- [ ] 1.8 Implement: add or adjust only the minimal test fixtures/public helpers needed for Long-term Context tests to pass.
- [ ] 1.9 Verify green: run `uv run pytest tests/integration -x -q`.

- [ ] 1.10 Write failing tests: Reflection contracts cover report generation, proposal lifecycle, KB reflection report and trend summary aggregation.
- [ ] 1.11 Implement: add or adjust only the minimal test fixtures/public helpers needed for Reflection tests to pass.
- [ ] 1.12 Verify green: run `uv run pytest tests/integration -x -q`.

- [ ] 1.13 Write failing tests: Vector Store contracts cover namespace isolation, reindex dry-run/apply and deterministic embedding/rerank provider behavior.
- [ ] 1.14 Implement: add or adjust only the minimal test fixtures/public helpers needed for Vector Store tests to pass.
- [ ] 1.15 Verify green: run `uv run pytest tests/integration -x -q`.

- [ ] 1.16 Write failing tests: Knowledge Base contracts cover local ingest, parser dispatch, sync planner, fake connector execution and search planner evidence.
- [ ] 1.17 Implement: add or adjust only the minimal test fixtures/public helpers needed for Knowledge Base tests to pass.
- [ ] 1.18 Verify green: run `uv run pytest tests/integration -x -q`.

- [ ] 1.19 Write failing tests: Deployment / Config contracts cover config fail-fast, backup/upgrade dry-run and diagnostics bundle boundaries.
- [ ] 1.20 Implement: add or adjust only the minimal test fixtures/public helpers needed for Deployment / Config tests to pass.
- [ ] 1.21 Verify green: run `uv run pytest tests/integration -x -q`.

## 2. Pilot acceptance E2E smoke

- [ ] 2.1 Write failing tests: local KB ingest -> agent KB binding -> agent query returns source attribution evidence.
- [ ] 2.2 Implement: add E2E fixture/harness using local docs, fake LLM and tmp SQLite so the path is deterministic.
- [ ] 2.3 Verify green: run `uv run pytest tests/e2e -x -q`.

- [ ] 2.4 Write failing tests: memory proposal/apply -> later agent/context run includes approved memory evidence.
- [ ] 2.5 Implement: add E2E fixture/harness using fake memory extraction signals and tmp SQLite.
- [ ] 2.6 Verify green: run `uv run pytest tests/e2e -x -q`.

- [ ] 2.7 Write failing tests: agent run -> admin query CLI returns readable trace, usage and performance evidence.
- [ ] 2.8 Implement: add deterministic CLI E2E fixture without real external providers.
- [ ] 2.9 Verify green: run `uv run pytest tests/e2e -x -q`.

- [ ] 2.10 Write failing tests: fake connector check -> dry-run sync -> execute sync -> latest status exposes actionable evidence.
- [ ] 2.11 Implement: add fake Google Drive / Confluence style connector E2E smoke or reuse existing fake connector fixtures.
- [ ] 2.12 Verify green: run `uv run pytest tests/e2e -x -q`.

## 3. Opt-in real smoke scaffolding

- [ ] 3.1 Write failing tests: real LLM / embedding / rerank smoke tests skip with clear reason when flags or credentials are absent.
- [ ] 3.2 Implement: add explicit opt-in environment gates and credential checks.
- [ ] 3.3 Verify green: run `uv run pytest tests/e2e tests/evaluation -x -q` with flags absent and confirm skips are readable.

- [ ] 3.4 Write failing tests: Google Drive / Confluence real smoke tests skip with clear reason when flags or credential refs are absent.
- [ ] 3.5 Implement: add explicit opt-in SaaS smoke gates and evidence capture.
- [ ] 3.6 Verify green: run `uv run pytest tests/e2e -x -q` with flags absent and confirm skips are readable.

## 4. Verification report

- [ ] 4.1 Write failing tests: report generator renders Markdown and JSON with run metadata, command results, per-capability evidence, real smoke skip/pass/fail and issue classification.
- [ ] 4.2 Implement: add report generator script/CLI and fixtures for deterministic report output.
- [ ] 4.3 Verify green: run report generator tests and `uv run pytest tests/unit tests/integration -x -q`.

- [ ] 4.4 Write failing tests: report maps failures to `Pilot blocker`, `Docs gap`, `Enhancement` or `Out-of-scope` and emits `Go`, `Conditional Go` or `No-Go`.
- [ ] 4.5 Implement: add classification model and final recommendation rules.
- [ ] 4.6 Verify green: run report generator tests and `uv run pytest tests/unit tests/integration -x -q`.

## 5. Documentation and final verification

- [ ] 5.1 Write failing tests or docs checks: `docs/capabilities/owner-capability-roadmap.md` and Pilot acceptance docs reference the new verification report entry point.
- [ ] 5.2 Implement: update docs with commands, expected artifacts and opt-in smoke flags.
- [ ] 5.3 Verify green: run `uv run pytest tests/integration -x -q` for docs/capability checks if applicable.
- [ ] 5.4 Run `uv run ruff format src tests scripts`.
- [ ] 5.5 Run `uv run ruff check src tests scripts`.
- [ ] 5.6 Run `uv run mypy src`.
- [ ] 5.7 Run `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`.
- [ ] 5.8 Run `uv run pytest -x -q`.
- [ ] 5.9 Run `openspec validate pilot-capability-verification-suite`.
