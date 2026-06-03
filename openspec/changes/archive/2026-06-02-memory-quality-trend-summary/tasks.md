# tasks

## 1. OpenSpec proposal

- [x] 1.1 Create proposal, design, tasks, and memory-layer spec delta
- [x] 1.2 Run `openspec validate 2026-06-02-memory-quality-trend-summary --strict`

## 2. Trend models and public API

- [x] 2.1 Write failing tests: import `MemoryQualityTrendQuery`, `MemoryQualityTrendBucket`, `MemoryQualityTrendSummary`, and `get_memory_quality_trend_summary`
- [x] 2.2 Verify red: run `uv run pytest tests/unit -x -q`
- [x] 2.3 Implement dataclasses and public API skeleton
- [x] 2.4 Verify green: run `uv run pytest tests/unit -x -q`

## 3. Memory and proposal aggregation

- [x] 3.1 Write failing tests: User Memory counts by type and expired context counts are bucketed
- [x] 3.2 Verify red: run `uv run pytest tests/integration -x -q`
- [x] 3.3 Implement User Memory aggregation
- [x] 3.4 Verify green: run `uv run pytest tests/integration -x -q`
- [x] 3.5 Write failing tests: Shared Memory counts remain separate from User Memory counts
- [x] 3.6 Verify red: run `uv run pytest tests/integration -x -q`
- [x] 3.7 Implement Shared Memory aggregation
- [x] 3.8 Verify green: run `uv run pytest tests/integration -x -q`
- [x] 3.9 Write failing tests: maintenance proposal status/action/risk counts are included
- [x] 3.10 Verify red: run `uv run pytest tests/integration -x -q`
- [x] 3.11 Implement proposal aggregation through reflection read boundary
- [x] 3.12 Verify green: run `uv run pytest tests/integration -x -q`

## 4. Evaluation and docs

- [x] 4.1 Write failing tests: deterministic evaluation covers duplicate reduction, expired context trend, and Shared Memory separation
- [x] 4.2 Verify red: run `uv run pytest tests/evaluation -x -q`
- [x] 4.3 Implement evaluation fixture/runner
- [x] 4.4 Verify green: run `uv run pytest tests/evaluation -x -q`
- [x] 4.5 Update `docs/capabilities/memory.md`; owner roadmap update is coordinated by parent

## 5. Verification

- [x] 5.1 Run `uv run ruff format src tests`
- [x] 5.2 Run `uv run ruff check src tests`
- [x] 5.3 Run `uv run mypy src`
- [x] 5.4 Run `uv run pytest -x -q`
- [x] 5.5 Run `openspec validate 2026-06-02-memory-quality-trend-summary --strict`
- [x] 5.6 Run `git diff --check`
