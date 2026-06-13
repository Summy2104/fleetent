# descope-layered-budget Design

## Context

`runtime/layered_budget.py`（AR18）跨 run 累计 session/user/agent 三层 turns/tokens 到 `agent_state.db.budget_usage`（PK `(scope,key,period)`），由 `loop.py` 每回合折入、`check()` 对比上限。功能完整（配置/example/5 测试文件/迁移俱全）但默认 `-1` 休眠。**已核实**：AR2 per-run budget（`runtime/budget.py`，`agent_max_turns`/`agent_max_tokens`/Grace Call）独立、零引用 layered；其 spec 家是 `agent-iteration-budget`（与本次删的 `agent-cost-budget` 是两个 spec）。`GovernanceConfig` 的 8 个 `agent_budget_*` 字段在 `agent_config.py` 与 `runtime/snapshot.py` 两处定义。当前 Y 最大版本以 apply 时为准。

## Goals / Non-Goals

**Goals:**
- 移净 AR18 跨 run 分层预算（模块/表/配置/接线/测试/文档/spec）
- per-run 预算（AR2）行为零变化
- descope 决策与重建路径留档，可逆

**Non-Goals:**
- 不动 AR2 per-run budget（`budget.py`、`agent_max_*`、Grace Call、`agent-iteration-budget` spec）
- 不迁移/保留 `budget_usage` 存量数据（上线前窗口，且表默认休眠多为空）
- 不为"将来重建"预留任何 stub/feature flag——干净删除，重建时从 git 历史取

## Decisions

**D1：整能力删除，不留休眠 stub / flag**
留半截（如保留配置字段但不接线）只会变成下一轮审计的"build-but-unwired"。干净删除：模块、表、配置、接线、测试、example、spec 一并移除。重建成本由完整的 git 历史 + decision-log 兜底，比留 stub 更清晰。

**D2：表删除走 Y 新版本 DROP（forward-only），不回填**
`agent_state_migrations.py` append `DROP TABLE budget_usage`（历史 CREATE 行保留——forward-only 不改历史，新版本推进），与 v25/v26 drop 旧提案表完全同模式。版本号不硬编码。存量行直接丢（默认休眠、上线前窗口）。

**D3：spec 全 6 条 REMOVED，能力 retire**
`agent-cost-budget` 的每条 requirement 都是跨 run 三层的（task 层明文"由 AR2 承载、本能力不另设"）——故整体 REMOVE，能力退役。per-run 在 `agent-iteration-budget` 有独立的家，spec 层面不受影响。每条 REMOVED 带 Reason + Migration（指向 AR2 + 重建路径）。

**D4：配置键移除后未知键不可 fail**
agent.yaml 里若已写 `agent_budget_*`，加载 GovernanceConfig 时移除字段后这些键变未知。apply 必须确认加载器对未知键宽容（忽略不报错），否则存量 example/配置会让启动崩。两处 GovernanceConfig（agent_config + snapshot）都要删字段并核实。

## Risks / Trade-offs

- [snapshot.py 的 GovernanceConfig 漏删字段 → 与 agent_config 不一致] → 两处同时删，加配置守护测试断言字段不存在
- [删 budget_usage 后 §3.3"11 张表"计数忘改] → 文档 task 显式要求改计数（→10）并删图块 + note ④
- [未知 `agent_budget_*` 键导致加载崩] → D4，apply 时以"带该键的 agent.yaml 仍能启动"测试确认
- [误删 AR2 per-run] → 边界已三次确认（budget.py 独立、agent_max_* 保留、agent-iteration-budget spec 不碰）；守护测试断言 per-run 预算仍生效

## Migration Plan

Y 新版本 DROP TABLE budget_usage（forward-only、不回填）。代码删除与迁移同 change 落地。回滚 = git revert（重建空表 + 恢复模块），但上线前窗口无需保数据。

## Open Questions

（无——descope 范围、AR2 保留、整删不留 stub 已与用户对齐。）
