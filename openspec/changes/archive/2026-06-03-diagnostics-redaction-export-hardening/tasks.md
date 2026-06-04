## 1. Manifest and artifact policy

- [x] 1.1 Write failing tests: diagnostics export writes a manifest with artifact names, kinds, redaction status and skipped reasons.
- [x] 1.2 Implement: add manifest model and deterministic manifest output.
- [x] 1.3 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

- [x] 1.4 Write failing tests: export excludes secret files, SQLite main DB, SQLite backups, full prompt/reply and KB document content by default.
- [x] 1.5 Implement: enforce default denylist and summary-only artifact policy.
- [x] 1.6 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

## 2. Redaction hardening

- [x] 2.1 Write failing tests: trace/config/connector summaries redact token-like, credential-like and bearer values.
- [x] 2.2 Implement: centralize diagnostics redaction helpers and apply them to all exported summaries.
- [x] 2.3 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

- [x] 2.4 Write failing tests: optional safe payload summary flag exports only truncated/redacted metadata, never raw transcript or KB body.
- [x] 2.5 Implement: add explicit safe payload summary mode with length limits and redaction markers.
- [x] 2.6 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

## 3. CLI/report integration

- [x] 3.1 Write failing tests: diagnostics admin CLI prints export path, manifest path, artifact count and skipped forbidden artifacts.
- [x] 3.2 Implement: update CLI output and return codes.
- [x] 3.3 Verify green: run `uv run pytest tests/integration -x -q`.

- [x] 3.4 Write failing tests: pilot verification report links diagnostics manifest as evidence when available.
- [x] 3.5 Implement: report artifact integration.
- [x] 3.6 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

## 4. Documentation and final checks

- [x] 4.1 Write failing docs/check tests if applicable: Pilot docs describe diagnostics package forbidden contents.
- [x] 4.2 Implement: update deployment docs and observability/deployment roadmap.
- [x] 4.3 Run `uv run ruff format src tests scripts`.
- [x] 4.4 Run `uv run ruff check src tests scripts`.
- [x] 4.5 Run `uv run mypy src`.
- [x] 4.6 Run `uv run pytest -x -q`.
- [x] 4.7 Run `openspec validate diagnostics-redaction-export-hardening`.
