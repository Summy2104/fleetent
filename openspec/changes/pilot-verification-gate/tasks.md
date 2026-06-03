## 1. Gate command model

- [ ] 1.1 Write failing tests: gate command model includes default checks, optional checks, command status, duration and artifact paths.
- [ ] 1.2 Implement: add typed gate result model and serialization.
- [ ] 1.3 Verify green: run `uv run pytest tests/unit -x -q`.

- [ ] 1.4 Write failing tests: gate includes pytest layers, OpenSpec validate, module boundary check and config validation.
- [ ] 1.5 Implement: add command runner or report adapter for required checks.
- [ ] 1.6 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

## 2. Recommendation rules

- [ ] 2.1 Write failing tests: failed required local checks produce `No-Go`.
- [ ] 2.2 Implement: final recommendation rules.
- [ ] 2.3 Verify green: run `uv run pytest tests/unit -x -q`.

- [ ] 2.4 Write failing tests: optional real smoke skipped status can still produce `Go` or `Conditional Go` depending on local evidence and issue classification.
- [ ] 2.5 Implement: real smoke skipped/pass/fail aggregation rules.
- [ ] 2.6 Verify green: run `uv run pytest tests/unit -x -q`.

## 3. Report output

- [ ] 3.1 Write failing tests: Markdown and JSON reports include command results, capability evidence, config validation, diagnostics manifest and real smoke statuses.
- [ ] 3.2 Implement: extend pilot verification report rendering.
- [ ] 3.3 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

- [ ] 3.4 Write failing tests: issues are classified into `Pilot blocker`, Docs gap, Enhancement or Out-of-scope.
- [ ] 3.5 Implement: issue classification summary and final gate section.
- [ ] 3.6 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

## 4. Documentation and final checks

- [ ] 4.1 Write failing docs/check tests if applicable: Pilot runbook documents the gate command and decision rules.
- [ ] 4.2 Implement: update docs and roadmaps.
- [ ] 4.3 Run `uv run ruff format src tests scripts`.
- [ ] 4.4 Run `uv run ruff check src tests scripts`.
- [ ] 4.5 Run `uv run mypy src`.
- [ ] 4.6 Run `uv run pytest -x -q`.
- [ ] 4.7 Run `openspec validate pilot-verification-gate`.
