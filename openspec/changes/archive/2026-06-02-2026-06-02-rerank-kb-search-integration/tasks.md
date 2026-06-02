## 1. Contract Tests
- [x] 1.1 Write failing unit tests for `search(..., mode="hybrid", rerank=True)` candidate pool sizing.
- [x] 1.2 Write failing unit tests for rerank provider ordering, illegal indexes, duplicate indexes and
      missing candidate append behavior.
- [x] 1.3 Write failing unit tests for rerank provider failure fallback to original hybrid order.
- [x] 1.4 Write failing unit tests that `rerank=True` with `mode="vector"` or `mode="keyword"` fails fast.
- [x] 1.5 Run `uv run pytest tests/unit -x -q` and confirm the new tests fail for the expected reasons.

## 2. Knowledge-Base Runtime
- [x] 2.1 Implement `search(..., rerank: bool = False)` and hybrid-only validation.
- [x] 2.2 Implement candidate pool constants and larger hybrid candidate gathering for rerank.
- [x] 2.3 Implement rerank provider invocation through the vector-store public rerank boundary.
- [x] 2.4 Implement result mapping, score replacement for reranked chunks and fallback ordering for missing
      candidates.
- [x] 2.5 Implement structured warning, and `kb_rerank_failed` trace event where an existing runtime event
      boundary is available without introducing a new dependency cycle.
- [x] 2.6 Run `uv run pytest tests/unit -x -q` and confirm the tests pass.

## 3. Integration And Evaluation
- [x] 3.1 Write failing integration tests with a fake reranker that changes hybrid result order.
- [x] 3.2 Write failing integration tests showing provider failure returns original hybrid results.
- [x] 3.3 Write failing deterministic evaluation coverage for reranked KB retrieval.
- [x] 3.4 Implement any required test fixtures or public exports.
- [x] 3.5 Run `uv run pytest tests/integration -x -q` and `uv run pytest tests/evaluation -x -q`.

## 4. Verification
- [x] 4.1 Run `uv run pytest -x -q`.
- [x] 4.2 Run `uv run ruff check src tests`.
- [x] 4.3 Run `uv run mypy src`.
- [x] 4.4 Run `openspec validate 2026-06-02-rerank-kb-search-integration --strict`.
