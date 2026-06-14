# agent-cost-budget Delta

> 本能力（AR18 跨 run 分层用量预算）v1 整体 descope。以下 6 条 requirement 全部移除。
> per-run 单次运行预算（`task` 层）不属本能力——归 `agent-iteration-budget`，不受影响。

## REMOVED Requirements

### Requirement: 五层用量预算层级
**Reason**: v1 简化——跨 run 分层用量预算为 opt-in 治理能力，默认休眠、pilot 期无人启用，先 descope。
**Migration**: 单次运行用量上限由 AR2 per-run `BudgetChecker`（`agent-iteration-budget`，`agent_max_turns`/`agent_max_tokens`/Grace Call）继续承载，未受影响。跨 run（session/user/agent）用量治理待真实需求出现时按需重建，完整设计见 git 历史与 `docs/records/decision-logs`。

### Requirement: 每层上限可配置且默认不拦截
**Reason**: 随分层预算能力整体 descope（见上）。
**Migration**: 8 个 `agent_budget_*` 配置键移除；per-run 的 `agent_max_turns`/`agent_max_tokens` 仍可配。

### Requirement: 跨运行累计持久化
**Reason**: 随分层预算能力整体 descope；`budget_usage` 表退役。
**Migration**: `agent_state.db.budget_usage` 经嵌入式 Y 新版本 DROP；无跨运行累计存储。重建时按原 `(scope, key, period)` 设计恢复。

### Requirement: 预算按窗口周期重置
**Reason**: 随分层预算能力整体 descope。
**Migration**: 无窗口/周期概念遗留；per-run 预算无窗口语义（单次运行内判定）。

### Requirement: 跨运行层聚合检查触发 budget_exceeded
**Reason**: 随分层预算能力整体 descope；聚合检查器移除。
**Migration**: per-run `BudgetChecker` 仍注册于 `TerminationController` 并按单次运行用量触发 `budget_exceeded` + Grace Call，跨运行聚合层不复存在。

### Requirement: 任一层超限触发 Grace Call 而非硬切断
**Reason**: 随分层预算能力整体 descope（Grace Call 路径本身归 AR2，未删）。
**Migration**: Grace Call 收尾路径由 `agent-iteration-budget` 的 per-run 预算继续触发；跨运行层触发入口移除。
