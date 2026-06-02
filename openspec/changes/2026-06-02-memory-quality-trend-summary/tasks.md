# tasks

## 1. OpenSpec proposal

- [ ] 1.1 Create proposal, design, tasks, and memory-layer spec delta
- [ ] 1.2 Run `openspec validate 2026-06-02-memory-quality-trend-summary --strict`

## 2. Trend models and public API

- [ ] 2.1 Write failing tests: import `MemoryQualityTrendQuery`, `MemoryQualityTrendBucket`, `MemoryQualityTrendSummary`, and `get_memory_quality_trend_summary`
- [ ] 2.2 Verify red: run `uv run pytest tests/unit -x -q`
- [ ] 2.3 Implement dataclasses and public API skeleton
- [ ] 2.4 Verify green: run `uv run pytest tests/unit -x -q`

## 3. Memory and proposal aggregation

- [ ] 3.1 Write failing tests: User Memory counts by type and expired context counts are bucketed
- [ ] 3.2 Verify red: run `uv run pytest tests/integration -x -q`
- [ ] 3.3 Implement User Memory aggregation
- [ ] 3.4 Verify green: run `uv run pytest tests/integration -x -q`
- [ ] 3.5 Write failing tests: Shared Memory counts remain separate from User Memory counts
- [ ] 3.6 Verify red: run `uv run pytest tests/integration -x -q`
- [ ] 3.7 Implement Shared Memory aggregation
- [ ] 3.8 Verify green: run `uv run pytest tests/integration -x -q`
- [ ] 3.9 Write failing tests: maintenance proposal status/action/risk counts are included
- [ ] 3.10 Verify red: run `uv run pytest tests/integration -x -q`
- [ ] 3.11 Implement proposal aggregation through reflection read boundary
- [ ] 3.12 Verify green: run `uv run pytest tests/integration -x -q`

## 4. Evaluation and docs

- [ ] 4.1 Write failing tests: deterministic evaluation covers duplicate reduction, expired context trend, and Shared Memory separation
- [ ] 4.2 Verify red: run `uv run pytest tests/evaluation -x -q`
- [ ] 4.3 Implement evaluation fixture/runner
- [ ] 4.4 Verify green: run `uv run pytest tests/evaluation -x -q`
- [ ] 4.5 Update `docs/capabilities/memory.md` and owner roadmap

## 5. Verification

- [ ] 5.1 Run `uv run ruff format src tests`
- [ ] 5.2 Run `uv run ruff check src tests`
- [ ] 5.3 Run `uv run mypy src`
- [ ] 5.4 Run `uv run pytest -x -q`
- [ ] 5.5 Run `openspec validate 2026-06-02-memory-quality-trend-summary --strict`
- [ ] 5.6 Run `git diff --check`
