# long-term-context-agent-tenant-policy

## Why

long-term-ctx 当前已经具备 User Memory + Knowledge Base 检索、agent KB binding、deterministic budget policy 和
source attribution。Shared Memory 数据层也已完成，但当前明确不接 prompt 注入。

下一步需要设计 agent / tenant 级上下文策略：哪些 agent 可使用 Shared Memory、不同来源的预算如何分配、
tenant 默认策略如何覆盖、冲突时 User Memory / Shared Memory / KB 谁优先。上游 API 已足够稳定，可以进入设计；
实现仍需后续单独 TDD。设计讨论后明确：policy 不应手写 arbitrary Shared Memory scopes，而应基于 agent
自身归属的 tenant / team 来解析 Shared Memory 范围。

## What Changes

- 新增 long-term context policy model：tenant default + agent override。
- 策略控制 provider enablement：User Memory、Shared Memory、Knowledge Base。
- 策略控制 per-source budget/top-k/conflict preference。
- 需要 agent 定义暴露归属：`tenant_id` 必填、`team_id` 可空。第一版只允许 agent 使用自身 tenant / team 的
  Shared Memory。
- Shared Memory 作为第三类 provider 接入 long-term-ctx 的设计边界，但不在本 change 实现。
- 默认策略保持当前行为：User Memory + KB，Shared Memory disabled，避免上线后改变 prompt。

## Out Of Scope

- 不实现代码，不 archive。
- 不定义 UI。
- 不做 LLM-driven planner、query rewrite 或 summarization。
- 不支持跨 tenant 或跨 team Shared Memory grant；如未来需要，单独设计 governance / grant spec。
- 不改变当前 `build_context()` 行为，直到实现 spec 执行。

## Module Boundary Impact

- owning package：`fleetent.intelligence.long_term_ctx`
- public API surface：`AgentContextIdentity`、`ContextPolicy`、`ContextPolicySourceBudget`、`resolve_context_policy()`；
  implementation 可选择扩展 `build_context()` 或新增 policy-aware wrapper
- owned tables：建议新增 `long_term_context_policies`；agent 归属字段由 agent-definition / agent management 表拥有
- config namespace：`long_term_ctx.policy.*`
- cross-module dependencies：依赖 memory public API 的 `search()` / `search_shared_memory()` 和 KB public `resolve_agent_kb_ids()` / `search()`
- migration / shim plan：新增 Alembic migration；如果 agent 表尚无 `tenant_id` / `team_id`，implementation 必须先通过 agent 边界补齐或依赖 agent management spec 提供；默认 backfill 不改变现有 runtime 行为
