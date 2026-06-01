## 0. 前置确认

- [x] 0.1 确认 `long-term-context-evaluation` 已完成，或本 change 只实现 policy contract 和单元 / 集成测试，不声称效果收益
- [x] 0.2 确认本 change 不做 LLM-driven selection / summarization / compression
- [x] 0.3 确认本 change 不做 memory 自动写回、删除、合并或 reflection maintenance
- [x] 0.4 确认本 change 不做 graph search、多 KB 绑定或真实 connector ACL 策略

## 1. Budget policy public API

- [x] 1.1 Write failing tests: 预算策略 dataclass 可从 `fleetent.intelligence.long_term_ctx` public API 导入
- [x] 1.2 Write failing tests: `BuiltContext` 返回预算元数据，且现有 `text` / `sources` 调用方继续可用
- [x] 1.3 Implement: 新增 budget policy dataclasses、预算元数据和 public exports
- [x] 1.4 Verify green: 运行 `uv run pytest tests/unit/test_long_term_context_budget_policy.py -x -q`

## 2. Config and effective budget

- [x] 2.1 Write failing tests: effective budget 取 `available_tokens` 与 `long_term_ctx.max_tokens` 的较小值
- [x] 2.2 Write failing tests: `available_tokens <= 0` 时短路，不调用 memory 或 knowledge provider，并记录 `zero_available_tokens`
- [x] 2.3 Write failing tests: 支持 `memory_max_tokens`、`knowledge_max_tokens`、`memory_top_k`、`knowledge_top_k` 和 `conflict_preference`
- [x] 2.4 Implement: config 读取、默认值和 effective budget 计算
- [x] 2.5 Verify green: 运行 `uv run pytest tests/unit/test_long_term_context_budget_policy.py -x -q`

## 3. Deterministic source selection

- [x] 3.1 Write failing tests: memory 和 knowledge 分别受 source token budget 限制
- [x] 3.2 Write failing tests: memory 和 knowledge 分别受 source top-k 限制
- [x] 3.3 Write failing tests: total budget 限制合并后的注入内容
- [x] 3.4 Write failing tests: 同分候选按稳定 source id tie-breaker 排序
- [x] 3.5 Implement: deterministic token estimator、source-aware ranking 和 budget trimming
- [x] 3.6 Verify green: 运行 `uv run pytest tests/unit/test_long_term_context_budget_policy.py -x -q`

## 4. Conflict preference

- [x] 4.1 Write failing tests: 事实 / 参考类 query 在 memory 和 KB 冲突时优先注入 KB
- [x] 4.2 Write failing tests: 个人偏好 / 历史类 query 在 memory 和 KB 冲突时优先注入 memory
- [x] 4.3 Write failing tests: `conflict_preference=memory` 或 `knowledge` 时覆盖 auto 判断
- [x] 4.4 Implement: deterministic query intent helper 和 conflict preference handling
- [x] 4.5 Verify green: 运行 `uv run pytest tests/unit/test_long_term_context_budget_policy.py -x -q`

## 5. Budget metadata and source attribution

- [x] 5.1 Write failing tests: 被注入来源记录 token estimate、source type 和 include reason
- [x] 5.2 Write failing tests: 被排除来源记录 `below_relevance_threshold`、`source_top_k_exceeded`、`source_budget_exceeded` 或 `total_budget_exceeded`
- [x] 5.3 Write failing tests: `BuiltContext.sources` 只包含实际注入的来源
- [x] 5.4 Implement: budget decision metadata and source filtering
- [x] 5.5 Verify green: 运行 `uv run pytest tests/unit/test_long_term_context_budget_policy.py -x -q`

## 6. Runtime integration

- [x] 6.1 Write failing tests: agent-runtime 仍通过现有 `build_context(user_id, query, agent_id, available_tokens)` 调用长期上下文
- [x] 6.2 Write failing tests: budget metadata 可通过现有 source attribution / runtime event 路径被 observability 消费或传递
- [x] 6.3 Implement: runtime integration fixes discovered by tests
- [x] 6.4 Verify green: 运行 `uv run pytest tests/integration/test_long_term_context_runtime.py -x -q`

## 7. Docs and final verification

- [x] 7.1 更新 `docs/capabilities/long-term-ctx.md`
- [x] 7.2 更新 `docs/capabilities/intelligence-roadmap.md`
- [x] 7.3 运行 `uv run ruff format src tests`
- [x] 7.4 运行 `uv run ruff check src tests`
- [x] 7.5 运行 `uv run mypy src`
- [x] 7.6 运行 `uv run pytest -x -q`
- [x] 7.7 运行 `openspec validate long-term-context-budget-policy --strict`
- [x] 7.8 运行 `git diff --check`
