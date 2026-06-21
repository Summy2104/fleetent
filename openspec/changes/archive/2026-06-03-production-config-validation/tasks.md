## 1. Validation model and secret scan

- [x] 1.1 Write failing tests: validation report can represent pass / warning / skipped / error items with stable JSON output.
- [x] 1.2 Implement: add typed validation report model and serializer.
- [x] 1.3 Verify green: run `uv run pytest tests/unit -x -q`.

- [x] 1.4 Write failing tests: settings/routes/MCP config containing inline secret-like values are classified as errors.
- [x] 1.5 Implement: add conservative secret-pattern scan over config values, excluding explicit placeholder examples.
- [x] 1.6 Verify green: run `uv run pytest tests/unit -x -q`.

## 2. Runtime prerequisite checks

- [x] 2.1 Write failing tests: DB URL, data dir, config dir and secrets dir checks report missing/unwritable paths clearly.
- [x] 2.2 Implement: add filesystem and database prerequisite checks without creating production data.
- [x] 2.3 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

- [x] 2.4 Write failing tests: provider route, embedding, rerank and connector credential_ref checks differ by `dev` / `pilot` / `production` profile.
- [x] 2.5 Implement: profile-aware validation rules (`dev` warning, `pilot` skipped, `production` error for required production dependencies).
- [x] 2.6 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

## 3. CLI and verification integration

- [x] 3.1 Write failing tests: `fleetent admin validate-config --profile pilot --format json` emits deterministic JSON summary.
- [x] 3.2 Implement: add admin CLI command and human-readable text output.
- [x] 3.3 Verify green: run `uv run pytest tests/integration -x -q`.

- [x] 3.4 Write failing tests: pilot verification report includes config validation status and skipped/error reasons.
- [x] 3.5 Implement: connect validation summary to pilot verification report.
- [x] 3.6 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

## 4. Documentation and final checks

- [x] 4.1 Write failing docs/check tests if applicable: Pilot runbook references `fleetent admin validate-config`.
- [x] 4.2 Implement: update deployment docs and roadmaps.
- [x] 4.3 Run `uv run ruff format src tests scripts`.
- [x] 4.4 Run `uv run ruff check src tests scripts`.
- [x] 4.5 Run `uv run mypy src`.
- [x] 4.6 Run `uv run pytest -x -q`.
- [x] 4.7 Run `openspec validate production-config-validation`.
