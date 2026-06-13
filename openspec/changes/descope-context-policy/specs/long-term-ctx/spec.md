# long-term-ctx Delta

## REMOVED Requirements

### Requirement: Agent tenant context policy design
**Reason**: per-tenant/agent 长期上下文源策略（`long_term_context_policies` 表 + `_policy.py` 全套）是建好+测了但生产零接线的休眠功能——读它的 `resolve_context_policy` / `build_context_with_policy` / `get_policy` / `upsert_policy` 在 src 无生产调用方。v1 简化直接 descope。
**Migration**: 生产的长期上下文组装仍由活路径承载——`build_context` → `_resolve_policy(available_tokens)` → `BudgetPolicy`（按 token 预算控制 User Memory + Knowledge Base 源，保留不变，见本 spec 的 Deterministic budget policy / Source budget limits / Conservative policy scope 等 requirement）。此 requirement 内含的 **shared-memory 进 long-term-context 的门控设计**本就未接线（生产中 shared-memory 未注入 context），随此一并 descope；shared-memory 的写/读本身（`memory/shared.py`、platform read projection）不受影响。日后若需"按 tenant/agent 策略门控上下文源 / shared-memory 进 context"，从 git 历史 + decision-log 重建。
