# tasks

## 1. OpenSpec proposal

- [x] 1.1 创建 proposal、design、tasks 和 knowledge-base spec delta
- [x] 1.2 运行 `openspec validate 2026-06-02-knowledge-base-graph-search --strict`

## 2. Graph search public models and API

- [x] 2.1 Write failing tests：public API 可导入 `graph_search`、`GraphSearchResult`、`GraphSearchChunk`、`EntityRef`、`RelationRef`
- [x] 2.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 2.3 Implement：新增 models 和 public exports
- [x] 2.4 Verify green：运行 `uv run pytest tests/unit -x -q`

## 3. Entity matching

- [x] 3.1 Write failing tests：normalized query 包含 entity normalized_name 时命中；不同 tenant / kb 不命中
- [x] 3.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 3.3 Implement：实现 deterministic entity matching query
- [x] 3.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 3.5 Write failing tests：entity metadata aliases 可参与 normalized matching
- [x] 3.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 3.7 Implement：支持 aliases matching
- [x] 3.8 Verify green：运行 `uv run pytest tests/unit -x -q`

## 4. Depth 0 direct entity graph search

- [x] 4.1 Write failing tests：`depth=0` 只返回 direct entity mention chunks，结果包含 matched_entities 和 evidence_chunk_ids
- [x] 4.2 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 4.3 Implement：实现 depth 0 graph_search
- [x] 4.4 Verify green：运行 `uv run pytest tests/integration -x -q`

## 5. Depth 1 relation expansion

- [x] 5.1 Write failing tests：`depth=1` 返回 direct chunks、relation evidence chunks 和 related entity mention chunks
- [x] 5.2 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 5.3 Implement：实现 relation expansion
- [x] 5.4 Verify green：运行 `uv run pytest tests/integration -x -q`
- [x] 5.5 Write failing tests：`related_to` / `conflicts_with` 双向展开；`depends_on` / `belongs_to` / `owns` / `defines` 单向展开；`mentions` 不展开
- [x] 5.6 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 5.7 Implement：补 direction-aware expansion
- [x] 5.8 Verify green：运行 `uv run pytest tests/integration -x -q`

## 6. Ranking, dedupe and limits

- [x] 6.1 Write failing tests：direct_entity_match=1.0、relation_evidence=0.8、related_entity_mention=0.6，按 score desc / position asc / chunk id asc 排序
- [x] 6.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 6.3 Implement：实现 deterministic scoring
- [x] 6.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 6.5 Write failing tests：同 chunk 多路径命中只返回一次，保留最高 score 并合并 evidence；limit 截断最终结果
- [x] 6.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 6.7 Implement：补 dedupe / evidence merge / limit
- [x] 6.8 Verify green：运行 `uv run pytest tests/unit -x -q`

## 7. API boundaries

- [x] 7.1 Write failing tests：`depth > 1` fail fast，`limit <= 0` 返回空结果
- [x] 7.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 7.3 Implement：补参数边界
- [x] 7.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 7.5 Write failing tests：`graph_search` 不改变现有 `search(..., mode=\"hybrid\")` 行为
- [x] 7.6 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 7.7 Implement：保持 graph_search 独立
- [x] 7.8 Verify green：运行 `uv run pytest tests/integration -x -q`

## 8. Evaluation fixtures

- [x] 8.1 Write failing tests：evaluation fixture 覆盖直接实体命中、客户隔离 forbidden chunk
- [x] 8.2 Verify red：运行 `uv run pytest tests/evaluation -x -q`
- [x] 8.3 Implement：新增 graph search evaluation fixture / runner
- [x] 8.4 Verify green：运行 `uv run pytest tests/evaluation -x -q`
- [x] 8.5 Write failing tests：evaluation fixture 覆盖一跳 relation expansion 和 directionality
- [x] 8.6 Verify red：运行 `uv run pytest tests/evaluation -x -q`
- [x] 8.7 Implement：补 relation / direction fixture
- [x] 8.8 Verify green：运行 `uv run pytest tests/evaluation -x -q`

## 9. Documentation

- [x] 9.1 Write failing tests：capability docs / roadmap 说明 graph_search 独立于 search、支持 depth 0/1 和 graph evidence，不接 query planner / rerank
- [x] 9.2 Verify red：运行相关文档测试或新增文档测试并确认失败
- [x] 9.3 Implement：更新 `docs/capabilities/knowledge-base.md` 和 `docs/capabilities/owner-capability-roadmap.md`
- [x] 9.4 Verify green：运行相关文档测试

## 10. 验证与归档

- [x] 10.1 运行 `uv run ruff format src tests`
- [x] 10.2 运行 `uv run ruff check src tests`
- [x] 10.3 运行 `uv run mypy src`
- [x] 10.4 运行 `uv run pytest -x -q`
- [x] 10.5 运行 `openspec validate 2026-06-02-knowledge-base-graph-search --strict`
- [x] 10.6 运行 `git diff --check`
- [x] 10.7 所有 checkbox 完成后归档 change 并验证 `openspec/specs/knowledge-base/spec.md`
