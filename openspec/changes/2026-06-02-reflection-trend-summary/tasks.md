# tasks

## 1. OpenSpec proposal

- [ ] 1.1 Create proposal, design, tasks, and reflection spec delta
- [ ] 1.2 Run `openspec validate 2026-06-02-reflection-trend-summary --strict`

## 2. Trend models and query API

- [ ] 2.1 Write failing tests: import `ReflectionTrendQuery`, `ReflectionTrendBucket`, `ReflectionTrendSummary`, and `get_reflection_trend_summary`
- [ ] 2.2 Verify red: run `uv run pytest tests/unit -x -q`
- [ ] 2.3 Implement dataclasses and public API skeleton
- [ ] 2.4 Verify green: run `uv run pytest tests/unit -x -q`

## 3. Report/proposal aggregation

- [ ] 3.1 Write failing tests: aggregate `reflection_reports` and `kb_reflection_reports` finding counts into UTC buckets
- [ ] 3.2 Verify red: run `uv run pytest tests/integration -x -q`
- [ ] 3.3 Implement report aggregation with redacted payload handling
- [ ] 3.4 Verify green: run `uv run pytest tests/integration -x -q`
- [ ] 3.5 Write failing tests: aggregate memory and skill proposal status/risk/type counts
- [ ] 3.6 Verify red: run `uv run pytest tests/integration -x -q`
- [ ] 3.7 Implement proposal aggregation
- [ ] 3.8 Verify green: run `uv run pytest tests/integration -x -q`

## 4. Evaluation and docs

- [ ] 4.1 Write failing tests: deterministic evaluation fixture covers trend direction and forbidden transcript snippets
- [ ] 4.2 Verify red: run `uv run pytest tests/evaluation -x -q`
- [ ] 4.3 Implement evaluation fixture/runner
- [ ] 4.4 Verify green: run `uv run pytest tests/evaluation -x -q`
- [ ] 4.5 Update `docs/capabilities/reflection.md` and owner roadmap

## 5. Verification

- [ ] 5.1 Run `uv run ruff format src tests`
- [ ] 5.2 Run `uv run ruff check src tests`
- [ ] 5.3 Run `uv run mypy src`
- [ ] 5.4 Run `uv run pytest -x -q`
- [ ] 5.5 Run `openspec validate 2026-06-02-reflection-trend-summary --strict`
- [ ] 5.6 Run `git diff --check`
