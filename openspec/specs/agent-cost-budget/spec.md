# agent-cost-budget Specification

## Purpose
TBD - created by archiving change cost-budget-control. Update Purpose after archive.
## Requirements

### Requirement: 五层成本预算层级

系统 SHALL 定义五个成本预算层级——单次任务（`task`）、单 session（`session`）、单用户（`user`）、单 agent（`agent`）、全局（`global`）——与 roadmap「运行治理·成本预算管控（五层）」一一对应。每层 SHALL 复用 AR2 的三个计量维度 `turns`（执行步数）/ `tokens`（token 用量）/ `cost_usd`（美元成本），不另立维度集。其中 `task` 层由 AR2 per-run `BudgetChecker` 承载（不重复判定、不另设配置），`session` / `user` / `agent` / `global` 四个跨运行层由本能力的聚合检查器承载，检查顺序 MUST 固定为由窄到宽（`session → user → agent → global`），多层同时超限时报告最窄层。

#### Scenario: 五层与维度齐备
- **WHEN** 查询可配置的预算层级与计量维度
- **THEN** 层级为 `task` / `session` / `user` / `agent` / `global` 五个，每层支持 `turns` / `tokens` / `cost_usd` 三维度

#### Scenario: 多层同超报最窄层
- **WHEN** `user` 层与 `global` 层同时达到各自上限
- **THEN** 触发层级报告为更窄的 `user`（由窄到宽顺序中的首个超限层）

### Requirement: 每层上限可配置且默认不拦截

每层预算上限 SHALL 经配置声明，复用 AR2 `BudgetConfig` 的 `{max_turns, max_tokens, max_cost_usd}` 与 `NO_LIMIT`（-1，表无上限）语义。任一层任一维度未配置时 MUST 默认为 `NO_LIMIT`（不拦截），以保证既有部署不被新层级意外拦截。配置 MUST 复用 `Settings`（env-first）字段惯例承载默认上限。

#### Scenario: 未配置层全部无上限
- **WHEN** 未为任何层配置预算上限
- **THEN** 五层各维度均为 `NO_LIMIT`，预算检查永不触发，运行行为与未引入本能力等价

#### Scenario: 单层单维度配置生效
- **WHEN** 仅为 `user` 层配置 `max_cost_usd=5.0`，其余层与维度未配置
- **THEN** 仅 `user` 层成本维度生效，其余层与维度仍为 `NO_LIMIT`

### Requirement: 跨运行累计持久化

`session` / `user` / `agent` / `global` 四层 SHALL 跨多次运行累计其 `turns` / `tokens` / `cost_usd` 用量，并以标准库 `sqlite3` 持久化（MUST NOT 使用 ORM 或 aiosqlite）。累计存储主键 MUST 为 `(scope, key, period)`，累加 MUST 经 `INSERT ... ON CONFLICT(scope, key, period) DO UPDATE` 原子完成（避免读-改-写竞态）。累计的单次增量换算 MUST 复用 AR2 `BudgetUsage.add(...)` 的口径（含 `MODEL_PRICING` / `DEFAULT_PRICING` 单价表），不得重新实现单价换算。累计键 SHALL 为 `session`→session_id、`user`→user_id、`agent`→agent_id、`global`→固定哨兵。`task` 层等价单次运行用量、由 AR2 per-run `BudgetChecker` 承载，MUST NOT 作为跨运行层落盘。持久化路径常量 MUST 可经 monkeypatch 注入以隔离测试。

#### Scenario: 同一用户同一周期内跨两次运行累计
- **WHEN** 同一 user_id 在同一窗口周期内先后完成两次运行，每次主循环消耗若干 token
- **THEN** 该 user 层在该 `period` 累计的 `turns` / `tokens` / `cost_usd` 为两次运行用量之和

#### Scenario: 不同键互不串扰
- **WHEN** 两个不同 user_id 各自运行
- **THEN** 各自累计独立，互不影响；`global` 层累计为两者之和且独立于任一 user 键

#### Scenario: task 不作为跨运行层落盘
- **WHEN** 一次运行结束
- **THEN** `task` 用量不写入跨运行累计存储（其预算由 AR2 per-run `BudgetChecker` 承载）

### Requirement: 预算按窗口周期重置

跨运行层的累计 SHALL 按**日历翻滚窗口**（tumbling window）重置：窗口取值集为 `{lifetime, daily, weekly, monthly}`。每层的 `period` SHALL 由**可注入时钟（UTC）**按该层窗口算出——`lifetime`→`"lifetime"`、`daily`→`"YYYY-MM-DD"`、`weekly`→ISO 周 `"YYYY-Www"`（周一起）、`monthly`→`"YYYY-MM"`。重置 MUST 通过 `period` 入主键（见「跨运行累计持久化」）涌现实现：跨周期后算出的 `period` 变化即落入新行、从 0 起累计，MUST NOT 依赖定时清零操作或调度器。各层默认窗口 SHALL 为 `session`→`lifetime`、`user`→`weekly`、`agent`→`weekly`、`global`→`monthly`。`user` / `agent` / `global` 三层窗口 SHALL 经 `Settings` 字段可配；`session` 固定 `lifetime` 不可配。窗口仅在该层配了上限时起作用。

#### Scenario: user 层 weekly 跨周归零
- **WHEN** 同一 user_id 在某 ISO 周累计了若干用量，时钟跨入下一 ISO 周后再次查询该层累计
- **THEN** 新周期的累计从 0 起（落入新 `period` 行），上一周累计不计入新周判定

#### Scenario: global 层 monthly 跨月归零
- **WHEN** `global` 层在某月累计了若干用量，时钟跨入下一月后再次查询
- **THEN** 新月的累计从 0 起，与上月各自独立成行

#### Scenario: lifetime 窗口永不重置
- **WHEN** `session` 层（窗口为 `lifetime`）随时钟推进经历多个日历周期
- **THEN** 其 `period` 恒为 `"lifetime"`，累计持续叠加、不随日历归零

#### Scenario: 各层默认窗口
- **WHEN** 未显式配置各层窗口
- **THEN** `session` 为 `lifetime`、`user` 为 `weekly`、`agent` 为 `weekly`、`global` 为 `monthly`

### Requirement: 跨运行层聚合检查触发 budget_exceeded

系统 SHALL 提供一个聚合检查器，实现 AR1 `TerminationChecker` 协议，仅对 **4 个跨运行层（`session` / `user` / `agent` / `global`）** 按由窄到宽顺序取当前周期累计用量并复用 AR2 `BudgetConfig.exhausted_dimension(usage)` 判定是否超限。`task` 层 MUST NOT 由该聚合检查器判定——它由 AR2 per-run `BudgetChecker` 承载，本能力不为其新增配置。任一跨运行层任一维度超限时，检查器 SHALL 返回 `StopReason.budget_exceeded`，并 MUST 记录触发层级与触发维度供运行日志归因。某层 `key` 缺失（如纯 CLI 运行无 session_id/user_id）时，该层 MUST 跳过检查（既不归入空 key、也不混入其他桶）。该检查器 MUST 注册到 `TerminationController`，与 AR2 单运行 `BudgetChecker` 并存。

#### Scenario: 某层超限返回 budget_exceeded
- **WHEN** `agent` 层当前周期累计 `cost_usd` 达到其配置上限
- **THEN** 聚合检查器返回 `StopReason.budget_exceeded`，并记录触发层级为 `agent`、触发维度为 `cost_usd`

#### Scenario: 各层均未超限不触发
- **WHEN** 各跨运行层累计用量均低于各自上限（或上限为 `NO_LIMIT`）
- **THEN** 聚合检查器返回 None，运行继续

#### Scenario: key 缺失跳过该层
- **WHEN** 一次纯 CLI 运行没有 session_id 与 user_id
- **THEN** 聚合检查器跳过 `session` 与 `user` 层检查，仅对有 key 的层（如 `agent` / `global`）判定，不将缺失 key 归入空桶

### Requirement: 系统内部操作豁免计入预算

系统内部 LLM 操作（上下文压缩、Grace Call 自身）MUST NOT 计入任何层级的预算累计。豁免 SHALL 沿用 AR2 契约——仅主循环推进用户任务的 LLM 调用进入累计入口，内部调用不接入该入口即豁免，不需额外豁免开关。

#### Scenario: 压缩调用不计入累计
- **WHEN** 一次运行中触发了上下文压缩
- **THEN** 压缩消耗的 token 不计入任何层级的累计用量

### Requirement: 任一层超限触发 Grace Call 而非硬切断

任一层级超限返回的 `StopReason.budget_exceeded` SHALL 复用 AR2 既有的 Grace Call 收尾路径——给模型最后一次机会生成进展总结，而非直接切断。本能力 MUST NOT 重写 Grace Call 逻辑或其 token 隔离比例（默认主预算 5%、保底 512，wave2 已决）。运行日志 SHALL 标注触发层级以区分由哪一层触发。

#### Scenario: 层级超限给出总结而非空响应
- **WHEN** `session` 层累计达到上限
- **THEN** 运行不被硬切断，而是经 `budget_exceeded` 走 Grace Call 给出当前进展总结；运行记录标注停止原因为 `budget_exceeded` 且触发层级为 `session`

### Requirement: 暴露预算剩余只读快照供成本感知路由

本能力 SHALL 提供一个只读快照生产者 `headroom()`，返回当前**最紧层的 cost 剩余比例**与该层名，供成本感知路由（MR2）消费。该生产者 MUST 复用本能力既有的跨运行层迭代内核（与聚合检查器同一套「遍历 `session` / `user` / `agent` / `global` 四层、读当前周期累计、对照各层上限」逻辑），MUST NOT 另写一套层级遍历或重算单价。

快照 SHALL 为只读值对象 `BudgetHeadroom`，至少含 `cost_remaining_ratio`（∈[0,1]，最紧层 `cost_usd` 剩余/上限）与 `tightest_scope`（最紧层名，供 trace 归因）。`headroom()` 对每个配置了 `cost_usd` 上限的层计算 `剩余比例 = (上限 - 当前周期累计) / 上限`，取最小者为 `cost_remaining_ratio`、其层名为 `tightest_scope`。未配置 `cost_usd` 上限的层 MUST NOT 参与计算；当无任何层配置 `cost_usd` 上限时，`cost_remaining_ratio` MUST 为 `1.0`（充裕）、`tightest_scope` MUST 为 None。某层 `key` 缺失时 MUST 跳过该层（沿用跨运行层聚合检查的 key 缺失处理）。该生产者 MUST 为只读快照——MUST NOT 修改任何层级的累计、检查或 Grace Call 行为。

类型 `BudgetHeadroom` 与生产者 `headroom()` MUST 归属本能力（分层预算），以保证消费方（MR2 路由）单向依赖本能力、本能力不反向依赖路由。

#### Scenario: 某层 cost 接近上限时剩余比例小且归因到该层
- **WHEN** `user` 层当前周期 `cost_usd` 累计已接近其配置上限，其余层未配 cost 上限或剩余更宽裕
- **THEN** `headroom()` 返回的 `cost_remaining_ratio` 为该最紧层的剩余比例（较小且 ∈[0,1]），`tightest_scope` 为 `user`

#### Scenario: 全无 cost 上限时充裕
- **WHEN** 没有任何跨运行层配置 `cost_usd` 上限
- **THEN** `headroom()` 返回 `cost_remaining_ratio` 为 `1.0`、`tightest_scope` 为 None

#### Scenario: 多层有 cost 上限时取最小剩余比例的层
- **WHEN** `user` 层与 `global` 层均配置了 `cost_usd` 上限，且 `global` 层当前剩余比例小于 `user` 层
- **THEN** `headroom()` 返回 `cost_remaining_ratio` 为 `global` 层的剩余比例，`tightest_scope` 为 `global`

#### Scenario: key 缺失层跳过不参与剩余计算
- **WHEN** 一次纯 CLI 运行无 session_id 与 user_id，但 `global` 层配了 `cost_usd` 上限
- **THEN** `headroom()` 跳过 `session` 与 `user` 层，仅以有 key 的 `global` 层计算剩余比例
