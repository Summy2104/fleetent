# knowledge-base-query-planner

## Why

Knowledge Base 已经逐步具备 vector、keyword、hybrid、graph search 和 rerank 能力。调用方如果直接选择底层
API，需要理解每种检索方式适用场景；后续管理面和 agent runtime 也需要知道“为什么这次用了 graph / hybrid /
rerank”。需要一个可解释、可测试的规则型 planner，把 retrieval 策略选择从底层 `search()` 中分离出来。

## What Changes

- 新增规则型 `plan_knowledge_search()` public API。
- 新增 `execute_knowledge_search_plan()` public API。
- planner 输出结构化 `KnowledgeSearchPlan`，包含 steps、reason、tenant_id、kb_ids、limit 和 options。
- 默认选择 hybrid search。
- 对 entity-like / relation-like query 先执行 graph search，不足时用 hybrid 补齐。
- `rerank=True` 只作用于 hybrid candidates。
- 记录可观测 reason，便于 trace、debug 和 evaluation。

## Out Of Scope

- 不接 LLM planner。
- 不做 query rewrite。
- 不修改现有 `search()` 行为，也不新增 `search(mode="auto")`。
- 不做 document-level ACL。
- 不做多轮 planner 或 agent tool chain planning。
- 不改变 graph search、hybrid search 或 rerank provider 的底层契约。

## Module Boundary Impact

- owning package：`fleetent.intelligence.knowledge_base`。
- public API surface：`KnowledgeSearchOptions`、`KnowledgeSearchPlan`、`KnowledgeSearchStep`、
  `plan_knowledge_search()`、`execute_knowledge_search_plan()`。
- owned tables：无。
- config namespace：无新增配置；规则常量留在 code。
- cross-module dependencies：使用 knowledge-base 内部 public retrieval APIs；可记录 observability event，但不强制引入新依赖。
- migration / shim plan：无 DB migration；不改 `search()` 兼容行为。
