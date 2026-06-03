# tasks

## 1. OpenSpec proposal

- [x] 1.1 创建 proposal、design、tasks 和 knowledge-base spec delta
- [x] 1.2 运行 `openspec validate 2026-06-02-knowledge-base-query-planner --strict`

## 2. Planner models and rules

- [x] 2.1 Write failing tests：public API 可导入 `KnowledgeSearchOptions`、`KnowledgeSearchPlan`、`KnowledgeSearchStep`、`plan_knowledge_search`
- [x] 2.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 2.3 Implement：新增 models 和 public exports
- [x] 2.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 2.5 Write failing tests：普通 query 生成 `hybrid_search` step，reason 为 `default_hybrid`
- [x] 2.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 2.7 Implement：实现 default hybrid rule
- [x] 2.8 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 2.9 Write failing tests：实体/关系型 query 生成 `graph_search` + `hybrid_fill`
- [x] 2.10 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 2.11 Implement：实现 deterministic entity/relation rule
- [x] 2.12 Verify green：运行 `uv run pytest tests/unit -x -q`

## 3. Rerank planning

- [x] 3.1 Write failing tests：`options.rerank=True` 时 hybrid step 标记 rerank，但 graph step 不 rerank
- [x] 3.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 3.3 Implement：实现 rerank_requested rule
- [x] 3.4 Verify green：运行 `uv run pytest tests/unit -x -q`

## 4. Plan execution

- [x] 4.1 Write failing tests：`execute_knowledge_search_plan()` 执行 default hybrid plan 并透传 tenant/kb/limit
- [x] 4.2 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 4.3 Implement：实现 hybrid execution
- [x] 4.4 Verify green：运行 `uv run pytest tests/integration -x -q`
- [x] 4.5 Write failing tests：graph plan 先返回 graph results，不足时用 hybrid fill，最终 dedupe 且不超过 limit
- [x] 4.6 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 4.7 Implement：实现 graph + fill execution 和 dedupe
- [x] 4.8 Verify green：运行 `uv run pytest tests/integration -x -q`
- [x] 4.9 Write failing tests：rerank plan 对 hybrid / fill 调用 rerank search path
- [x] 4.10 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 4.11 Implement：接入 rerank hybrid path
- [x] 4.12 Verify green：运行 `uv run pytest tests/integration -x -q`

## 5. Observability and evaluation

- [x] 5.1 Write failing tests：planner / executor 记录 selected steps、reasons、fallback counts 的 structured event 或 log
- [x] 5.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 5.3 Implement：补 observability/logging
- [x] 5.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 5.5 Write failing tests：deterministic evaluation 覆盖 ordinary / relation / rerank query plan
- [x] 5.6 Verify red：运行 `uv run pytest tests/evaluation -x -q`
- [x] 5.7 Implement：新增 planner evaluation fixture / runner
- [x] 5.8 Verify green：运行 `uv run pytest tests/evaluation -x -q`

## 6. Documentation and verification

- [x] 6.1 Write failing tests：capability docs / roadmap 说明 planner 为规则型独立 API，不改 `search()` 且不接 LLM
- [x] 6.2 Verify red：运行相关文档测试
- [x] 6.3 Implement：更新 `docs/capabilities/knowledge-base.md` 和 `docs/capabilities/owner-capability-roadmap.md`
- [x] 6.4 Verify green：运行相关文档测试
- [x] 6.5 运行 `uv run ruff format src tests`
- [x] 6.6 运行 `uv run ruff check src tests`
- [x] 6.7 运行 `uv run mypy src`
- [x] 6.8 运行 `uv run pytest -x -q`
- [x] 6.9 运行 `openspec validate 2026-06-02-knowledge-base-query-planner --strict`
- [x] 6.10 运行 `git diff --check`
