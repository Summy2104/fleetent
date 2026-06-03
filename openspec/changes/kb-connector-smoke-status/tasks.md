## 1. Connector status contract

- [ ] 1.1 Write failing tests: latest status includes connector id, source scope, last check, last dry-run, last sync, failures, skipped reason and redacted credential_ref.
- [ ] 1.2 Implement: add/extend connector status DTO and persistence if needed.
- [ ] 1.3 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

- [ ] 1.4 Write failing tests: status never includes credential payload or raw token values.
- [ ] 1.5 Implement: redaction and serialization guards.
- [ ] 1.6 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

## 2. Fake and real smoke

- [ ] 2.1 Write failing tests: fake connector smoke covers check -> dry-run sync -> execute sync -> latest status.
- [ ] 2.2 Implement: deterministic fake smoke harness.
- [ ] 2.3 Verify green: run `uv run pytest tests/e2e tests/integration -x -q`.

- [ ] 2.4 Write failing tests: real Google Drive / Confluence smoke skips with clear reason when opt-in flags or credential_refs are absent.
- [ ] 2.5 Implement: real smoke gates and skip reasons.
- [ ] 2.6 Verify green: run `uv run pytest tests/e2e -x -q`.

- [ ] 2.7 Write failing tests: real execute sync requires a second opt-in flag beyond check/dry-run.
- [ ] 2.8 Implement: separate real execute sync opt-in and fixture source guard.
- [ ] 2.9 Verify green: run `uv run pytest tests/e2e -x -q`.

## 3. Report and docs

- [ ] 3.1 Write failing tests: pilot verification report includes connector status and real smoke skip/pass/fail evidence.
- [ ] 3.2 Implement: report integration.
- [ ] 3.3 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

- [ ] 3.4 Write failing docs/check tests if applicable: docs explain check/dry-run vs execute sync opt-in.
- [ ] 3.5 Implement: update KB, deployment and intelligence roadmap docs.
- [ ] 3.6 Run `uv run ruff format src tests scripts`.
- [ ] 3.7 Run `uv run ruff check src tests scripts`.
- [ ] 3.8 Run `uv run mypy src`.
- [ ] 3.9 Run `uv run pytest -x -q`.
- [ ] 3.10 Run `openspec validate kb-connector-smoke-status`.
