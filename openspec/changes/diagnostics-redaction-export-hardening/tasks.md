## 1. Manifest and artifact policy

- [ ] 1.1 Write failing tests: diagnostics export writes a manifest with artifact names, kinds, redaction status and skipped reasons.
- [ ] 1.2 Implement: add manifest model and deterministic manifest output.
- [ ] 1.3 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

- [ ] 1.4 Write failing tests: export excludes secret files, SQLite main DB, SQLite backups, full prompt/reply and KB document content by default.
- [ ] 1.5 Implement: enforce default denylist and summary-only artifact policy.
- [ ] 1.6 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

## 2. Redaction hardening

- [ ] 2.1 Write failing tests: trace/config/connector summaries redact token-like, credential-like and bearer values.
- [ ] 2.2 Implement: centralize diagnostics redaction helpers and apply them to all exported summaries.
- [ ] 2.3 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

- [ ] 2.4 Write failing tests: optional safe payload summary flag exports only truncated/redacted metadata, never raw transcript or KB body.
- [ ] 2.5 Implement: add explicit safe payload summary mode with length limits and redaction markers.
- [ ] 2.6 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

## 3. CLI/report integration

- [ ] 3.1 Write failing tests: diagnostics admin CLI prints export path, manifest path, artifact count and skipped forbidden artifacts.
- [ ] 3.2 Implement: update CLI output and return codes.
- [ ] 3.3 Verify green: run `uv run pytest tests/integration -x -q`.

- [ ] 3.4 Write failing tests: pilot verification report links diagnostics manifest as evidence when available.
- [ ] 3.5 Implement: report artifact integration.
- [ ] 3.6 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

## 4. Documentation and final checks

- [ ] 4.1 Write failing docs/check tests if applicable: Pilot docs describe diagnostics package forbidden contents.
- [ ] 4.2 Implement: update deployment docs and observability/deployment roadmap.
- [ ] 4.3 Run `uv run ruff format src tests scripts`.
- [ ] 4.4 Run `uv run ruff check src tests scripts`.
- [ ] 4.5 Run `uv run mypy src`.
- [ ] 4.6 Run `uv run pytest -x -q`.
- [ ] 4.7 Run `openspec validate diagnostics-redaction-export-hardening`.
