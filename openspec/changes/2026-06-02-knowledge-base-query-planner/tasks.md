# tasks

## 1. OpenSpec proposal

- [ ] 1.1 创建 proposal、design、tasks 和 knowledge-base spec delta
- [ ] 1.2 运行 `openspec validate 2026-06-02-knowledge-base-query-planner --strict`

## 2. Planner models and rules

- [ ] 2.1 Write failing tests：public API 可导入 `KnowledgeSearchOptions`、`KnowledgeSearchPlan`、`KnowledgeSearchStep`、`plan_knowledge_search`
- [ ] 2.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 2.3 Implement：新增 models 和 public exports
- [ ] 2.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [ ] 2.5 Write failing tests：普通 query 生成 `hybrid_search` step，reason 为 `default_hybrid`
- [ ] 2.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 2.7 Implement：实现 default hybrid rule
- [ ] 2.8 Verify green：运行 `uv run pytest tests/unit -x -q`
- [ ] 2.9 Write failing tests：实体/关系型 query 生成 `graph_search` + `hybrid_fill`
- [ ] 2.10 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 2.11 Implement：实现 deterministic entity/relation rule
- [ ] 2.12 Verify green：运行 `uv run pytest tests/unit -x -q`

## 3. Rerank planning

- [ ] 3.1 Write failing tests：`options.rerank=True` 时 hybrid step 标记 rerank，但 graph step 不 rerank
- [ ] 3.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 3.3 Implement：实现 rerank_requested rule
- [ ] 3.4 Verify green：运行 `uv run pytest tests/unit -x -q`

## 4. Plan execution

- [ ] 4.1 Write failing tests：`execute_knowledge_search_plan()` 执行 default hybrid plan 并透传 tenant/kb/limit
- [ ] 4.2 Verify red：运行 `uv run pytest tests/integration -x -q`
- [ ] 4.3 Implement：实现 hybrid execution
- [ ] 4.4 Verify green：运行 `uv run pytest tests/integration -x -q`
- [ ] 4.5 Write failing tests：graph plan 先返回 graph results，不足时用 hybrid fill，最终 dedupe 且不超过 limit
- [ ] 4.6 Verify red：运行 `uv run pytest tests/integration -x -q`
- [ ] 4.7 Implement：实现 graph + fill execution 和 dedupe
- [ ] 4.8 Verify green：运行 `uv run pytest tests/integration -x -q`
- [ ] 4.9 Write failing tests：rerank plan 对 hybrid / fill 调用 rerank search path
- [ ] 4.10 Verify red：运行 `uv run pytest tests/integration -x -q`
- [ ] 4.11 Implement：接入 rerank hybrid path
- [ ] 4.12 Verify green：运行 `uv run pytest tests/integration -x -q`

## 5. Observability and evaluation

- [ ] 5.1 Write failing tests：planner / executor 记录 selected steps、reasons、fallback counts 的 structured event 或 log
- [ ] 5.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 5.3 Implement：补 observability/logging
- [ ] 5.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [ ] 5.5 Write failing tests：deterministic evaluation 覆盖 ordinary / relation / rerank query plan
- [ ] 5.6 Verify red：运行 `uv run pytest tests/evaluation -x -q`
- [ ] 5.7 Implement：新增 planner evaluation fixture / runner
- [ ] 5.8 Verify green：运行 `uv run pytest tests/evaluation -x -q`

## 6. Documentation and verification

- [ ] 6.1 Write failing tests：capability docs / roadmap 说明 planner 为规则型独立 API，不改 `search()` 且不接 LLM
- [ ] 6.2 Verify red：运行相关文档测试
- [ ] 6.3 Implement：更新 `docs/capabilities/knowledge-base.md` 和 `docs/capabilities/owner-capability-roadmap.md`
- [ ] 6.4 Verify green：运行相关文档测试
- [ ] 6.5 运行 `uv run ruff format src tests`
- [ ] 6.6 运行 `uv run ruff check src tests`
- [ ] 6.7 运行 `uv run mypy src`
- [ ] 6.8 运行 `uv run pytest -x -q`
- [ ] 6.9 运行 `openspec validate 2026-06-02-knowledge-base-query-planner --strict`
- [ ] 6.10 运行 `git diff --check`
