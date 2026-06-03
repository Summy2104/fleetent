# tasks

## 1. OpenSpec proposal

- [x] 1.1 Create proposal, design, tasks, and reflection spec delta
- [x] 1.2 Run `openspec validate 2026-06-02-reflection-trend-summary --strict`

## 2. Trend models and query API

- [x] 2.1 Write failing tests: import `ReflectionTrendQuery`, `ReflectionTrendBucket`, `ReflectionTrendSummary`, and `get_reflection_trend_summary`
- [x] 2.2 Verify red: run `uv run pytest tests/unit -x -q`
- [x] 2.3 Implement dataclasses and public API skeleton
- [x] 2.4 Verify green: run `uv run pytest tests/unit -x -q`

## 3. Report/proposal aggregation

- [x] 3.1 Write failing tests: aggregate `reflection_reports` and `kb_reflection_reports` finding counts into UTC buckets
- [x] 3.2 Verify red: run `uv run pytest tests/integration -x -q`
- [x] 3.3 Implement report aggregation with redacted payload handling
- [x] 3.4 Verify green: run `uv run pytest tests/integration -x -q`
- [x] 3.5 Write failing tests: aggregate memory and skill proposal status/risk/type counts
- [x] 3.6 Verify red: run `uv run pytest tests/integration -x -q`
- [x] 3.7 Implement proposal aggregation
- [x] 3.8 Verify green: run `uv run pytest tests/integration -x -q`

## 4. Evaluation and docs

- [x] 4.1 Write failing tests: deterministic evaluation fixture covers trend direction and forbidden transcript snippets
- [x] 4.2 Verify red: run `uv run pytest tests/evaluation -x -q`
- [x] 4.3 Implement evaluation fixture/runner
- [x] 4.4 Verify green: run `uv run pytest tests/evaluation -x -q`
- [x] 4.5 Update `docs/capabilities/reflection.md`; owner roadmap intentionally deferred to parent coordination

## 5. Verification

- [x] 5.1 Run `uv run ruff format src tests`
- [x] 5.2 Run `uv run ruff check src tests`
- [x] 5.3 Run `uv run mypy src`
- [x] 5.4 Run `uv run pytest -x -q`
- [x] 5.5 Run `openspec validate 2026-06-02-reflection-trend-summary --strict`
- [x] 5.6 Run `git diff --check`
