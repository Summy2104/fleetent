# Design

## Planner Shape

第一版 planner 是 deterministic rules，不使用 LLM。它只负责选择和解释 retrieval steps：

```python
plan = plan_knowledge_search(
    query="Acme 的 SSO 依赖哪个系统？",
    tenant_id="default",
    kb_ids=["global", "customer-acme"],
    limit=10,
    options=KnowledgeSearchOptions(rerank=True),
)

results = await execute_knowledge_search_plan(plan)
```

`search(mode="vector|keyword|hybrid")` 保持底层检索 API，不增加 `auto` mode。

## Plan Model

`KnowledgeSearchPlan`：

- `query`
- `tenant_id`
- `kb_ids`
- `limit`
- `options`
- `steps`
- `reasons`

`KnowledgeSearchStep`：

- `kind`: `hybrid_search`、`graph_search`、`hybrid_fill`、`hybrid_rerank`
- `reason`: `default_hybrid`、`entity_like_query`、`relation_like_query`、`graph_fill`、`rerank_requested`
- `limit`
- `metadata`

## Rules

第一版规则保持可解释和可测试：

1. `limit <= 0` 返回 empty plan / empty result。
2. 默认 plan：`hybrid_search`。
3. query 出现实体/关系迹象时，先 `graph_search`：
   - 包含已知 relation keywords，例如 “依赖”、“属于”、“拥有”、“定义”、“冲突”、“影响”、“关联”。
   - 包含 customer / system / project-like token；实现可用 deterministic keyword / capitalization / existing entity match。
4. graph result 数量不足 `limit` 时，追加 `hybrid_fill` 补齐。
5. `options.rerank=True` 时，对 hybrid / hybrid_fill 使用 `search(..., mode="hybrid", rerank=True)` 或等价 rerank integration。
6. graph results 不在第一版强行 rerank，避免混合 graph score 和 rerank score。

## Execution

`execute_knowledge_search_plan()` 按 steps 执行并去重：

- graph 和 hybrid 结果都映射为统一 result wrapper，保留 source kind 和 reason。
- 同一 chunk 多 step 命中只返回一次；graph result 优先保留 graph evidence，hybrid score 作为补充 metadata。
- 最终返回数量不超过 plan limit。

## Observability

planner 应记录轻量事件或 structured log：

- selected steps；
- reasons；
- graph count；
- hybrid fill count；
- rerank requested；
- fallback / empty result。

如果当前 runtime trace boundary 不可用，至少记录 structured debug/warning，不引入 dependency cycle。

## Evaluation

新增 deterministic evaluation fixture：

- 普通问题选择 hybrid；
- 关系型问题选择 graph + hybrid fill；
- `rerank=True` 只影响 hybrid；
- forbidden chunk 不因 planner fallback 被排到 top。
