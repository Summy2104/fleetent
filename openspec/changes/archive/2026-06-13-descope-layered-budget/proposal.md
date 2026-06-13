# descope-layered-budget

## Why

跨 run 分层用量预算（AR18 layered budget：session/user/agent 三层 turns/tokens 累计 + `budget_usage` 表）是一个完整接通、有测试、有文档的 **opt-in 治理功能**，但默认全 `-1`（无上限）即休眠，pilot 期无人启用。实体关系审计时确认它在数据模型里是孤岛（计数器表，多态 `key`），且还带两个未解的语义/运维缺口（user-scope 实为 per-(user,agent) 不可表达全局；`budget_usage` 行只增不减无 TTL）。v1 决定**先做简单**：砍掉这个未启用的能力，留待真有跨 run 用量治理需求时按需重建（设计完整保存在 git 历史 + decision-log，加得回）。**per-run 单次运行预算（AR2 `runtime/budget.py`，`agent_max_turns`/`agent_max_tokens`/Grace Call）是独立能力，完全保留**——单次失控仍被它兜住。

## What Changes

- **删模块**：`runtime/layered_budget.py` 整个移除（`BudgetScope`/`BudgetWindow`/`LayeredBudgetChecker`/`BudgetStore` 等）
- **删表**：`agent_state.db.budget_usage` —— `agent_state_migrations.py` 追加新版本 `DROP TABLE budget_usage`（嵌入式 Y forward-only：历史 CREATE 行保留、新版本 drop，同 v25/v26 drop 旧提案表模式；版本号不硬编码，append 在当前最大版本之后）
- **删配置**：`agent_config.GovernanceConfig` 与 `runtime/snapshot.GovernanceConfig` 各删 8 个字段（`agent_budget_{session,user,agent}_{turns,tokens}` + `agent_budget_{user,agent}_window`）；**保留** `agent_max_turns`/`agent_max_tokens`/`agent_grace_*`（AR2 per-run，不是这 8 个）
- **删接线**：`runtime/loop.py` 的 `_setup_layered_budget` / `_layered_budget_add` 及调用点；`runtime/agent_app.py` 的 `layered_budget` import + `set_state_db`
- **删 example**：`agents/default/agent.yaml.example` 的 layered budget 段 + 头部注释里的 `agent_budget_*` 提及
- **删测试**：`test_layered_budget` / `test_layered_budget_per_agent` / `test_layered_budget_store` / `test_budget_usage_migration`；`test_agent_config_governance` 中 layered 字段断言；新增守护断言（模块/表/配置字段已不存在）
- **文档**：`data-model.md` §3.1 去 `budget_usage` 节点、§3.3 表清单"11 张表"→"10 张表"并删图中 `budget_usage` 块 + 删 note ④（scope 枚举那条）；decision-log 追记 descope 决策（为什么砍、AR2 保留、将来怎么加回）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `agent-cost-budget`: **整个能力 v1 descope** —— 6 条 requirement 全部 REMOVED（五层层级 / 每层上限可配 / 跨运行累计持久化 / 窗口周期重置 / 跨运行聚合检查 / 任一层超限触发 Grace Call）。per-run task 层不在本 spec（归 `agent-iteration-budget`，不受影响）

## Impact

- **owning package**：`runtime`（layered_budget 删除、agent_state_migrations drop、loop/agent_app/snapshot 接线清理）、顶层 `agent_config.py`
- **public API surface**：移除 `runtime.layered_budget` 模块全部导出；`GovernanceConfig`（agent_config + snapshot 两处）移除 8 个 `agent_budget_*` 字段；`loop` 内部 helper 移除
- **owned tables**：`agent_state.db` drop `budget_usage`（嵌入式 Y 新版本，forward-only）
- **config namespace**：移除 8 个 `agent_budget_*` governance 键（agent.yaml 中已配该键的部署：键被忽略不报错——apply 时确认未知键不 fail；属上线前窗口，无存量部署依赖）
- **cross-module dependencies**：无新增；AR2 per-run budget（`runtime/budget.py` + `agent-iteration-budget` spec）独立、零触碰
- **migration / shim plan**：Y 新版本 DROP TABLE（forward-only，存量 `budget_usage` 数据丢弃——上线前窗口、且该表默认休眠多为空）；无代码 shim
- **相邻切片**：apply 前 `git pull` 确认无在跑 change 触碰 reflection/budget/loop 区域
