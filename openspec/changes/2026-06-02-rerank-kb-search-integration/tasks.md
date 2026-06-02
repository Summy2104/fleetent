## 1. Contract Tests
- [ ] 1.1 Write failing unit tests for `search(..., mode="hybrid", rerank=True)` candidate pool sizing.
- [ ] 1.2 Write failing unit tests for rerank provider ordering, illegal indexes, duplicate indexes and
      missing candidate append behavior.
- [ ] 1.3 Write failing unit tests for rerank provider failure fallback to original hybrid order.
- [ ] 1.4 Write failing unit tests that `rerank=True` with `mode="vector"` or `mode="keyword"` fails fast.
- [ ] 1.5 Run `uv run pytest tests/unit -x -q` and confirm the new tests fail for the expected reasons.

## 2. Knowledge-Base Runtime
- [ ] 2.1 Implement `search(..., rerank: bool = False)` and hybrid-only validation.
- [ ] 2.2 Implement candidate pool constants and larger hybrid candidate gathering for rerank.
- [ ] 2.3 Implement rerank provider invocation through the vector-store public rerank boundary.
- [ ] 2.4 Implement result mapping, score replacement for reranked chunks and fallback ordering for missing
      candidates.
- [ ] 2.5 Implement structured warning, and `kb_rerank_failed` trace event where an existing runtime event
      boundary is available without introducing a new dependency cycle.
- [ ] 2.6 Run `uv run pytest tests/unit -x -q` and confirm the tests pass.

## 3. Integration And Evaluation
- [ ] 3.1 Write failing integration tests with a fake reranker that changes hybrid result order.
- [ ] 3.2 Write failing integration tests showing provider failure returns original hybrid results.
- [ ] 3.3 Write failing deterministic evaluation coverage for reranked KB retrieval.
- [ ] 3.4 Implement any required test fixtures or public exports.
- [ ] 3.5 Run `uv run pytest tests/integration -x -q` and `uv run pytest tests/evaluation -x -q`.

## 4. Verification
- [ ] 4.1 Run `uv run pytest -x -q`.
- [ ] 4.2 Run `uv run ruff check src tests`.
- [ ] 4.3 Run `uv run mypy src`.
- [ ] 4.4 Run `openspec validate 2026-06-02-rerank-kb-search-integration --strict`.
