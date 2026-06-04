## 1. Connector status contract

- [x] 1.1 Write failing tests: latest status includes connector id, source scope, last check, last dry-run, last sync, failures, skipped reason and redacted credential_ref.
- [x] 1.2 Implement: add/extend connector status DTO and persistence if needed.
- [x] 1.3 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

- [x] 1.4 Write failing tests: status never includes credential payload or raw token values.
- [x] 1.5 Implement: redaction and serialization guards.
- [x] 1.6 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

## 2. Fake and real smoke

- [x] 2.1 Write failing tests: fake connector smoke covers check -> dry-run sync -> execute sync -> latest status.
- [x] 2.2 Implement: deterministic fake smoke harness.
- [x] 2.3 Verify green: run `uv run pytest tests/e2e tests/integration -x -q`.

- [x] 2.4 Write failing tests: real Google Drive / Confluence smoke skips with clear reason when opt-in flags or credential_refs are absent.
- [x] 2.5 Implement: real smoke gates and skip reasons.
- [x] 2.6 Verify green: run `uv run pytest tests/e2e -x -q`.

- [x] 2.7 Write failing tests: real execute sync requires a second opt-in flag beyond check/dry-run.
- [x] 2.8 Implement: separate real execute sync opt-in and fixture source guard.
- [x] 2.9 Verify green: run `uv run pytest tests/e2e -x -q`.

## 3. Report and docs

- [x] 3.1 Write failing tests: pilot verification report includes connector status and real smoke skip/pass/fail evidence.
- [x] 3.2 Implement: report integration.
- [x] 3.3 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

- [x] 3.4 Write failing docs/check tests if applicable: docs explain check/dry-run vs execute sync opt-in.
- [x] 3.5 Implement: update KB, deployment and intelligence roadmap docs.
- [x] 3.6 Run `uv run ruff format src tests scripts`.
- [x] 3.7 Run `uv run ruff check src tests scripts`.
- [x] 3.8 Run `uv run mypy src`.
- [x] 3.9 Run `uv run pytest -x -q`.
- [x] 3.10 Run `openspec validate kb-connector-smoke-status`.
