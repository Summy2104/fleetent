## 1. Gate command model

- [x] 1.1 Write failing tests: gate command model includes default checks, optional checks, command status, duration and artifact paths.
- [x] 1.2 Implement: add typed gate result model and serialization.
- [x] 1.3 Verify green: run `uv run pytest tests/unit -x -q`.

- [x] 1.4 Write failing tests: gate includes pytest layers, OpenSpec validate, module boundary check and config validation.
- [x] 1.5 Implement: add command runner or report adapter for required checks.
- [x] 1.6 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

## 2. Recommendation rules

- [x] 2.1 Write failing tests: failed required local checks produce `No-Go`.
- [x] 2.2 Implement: final recommendation rules.
- [x] 2.3 Verify green: run `uv run pytest tests/unit -x -q`.

- [x] 2.4 Write failing tests: optional real smoke skipped status can still produce `Go` or `Conditional Go` depending on local evidence and issue classification.
- [x] 2.5 Implement: real smoke skipped/pass/fail aggregation rules.
- [x] 2.6 Verify green: run `uv run pytest tests/unit -x -q`.

## 3. Report output

- [x] 3.1 Write failing tests: Markdown and JSON reports include command results, capability evidence, config validation, diagnostics manifest and real smoke statuses.
- [x] 3.2 Implement: extend pilot verification report rendering.
- [x] 3.3 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

- [x] 3.4 Write failing tests: issues are classified into `Pilot blocker`, Docs gap, Enhancement or Out-of-scope.
- [x] 3.5 Implement: issue classification summary and final gate section.
- [x] 3.6 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

## 4. Documentation and final checks

- [x] 4.1 Write failing docs/check tests if applicable: Pilot runbook documents the gate command and decision rules.
- [x] 4.2 Implement: update docs and roadmaps.
- [x] 4.3 Run `uv run ruff format src tests scripts`.
- [x] 4.4 Run `uv run ruff check src tests scripts`.
- [x] 4.5 Run `uv run mypy src`.
- [x] 4.6 Run `uv run pytest -x -q`.
- [x] 4.7 Run `openspec validate pilot-verification-gate`.
