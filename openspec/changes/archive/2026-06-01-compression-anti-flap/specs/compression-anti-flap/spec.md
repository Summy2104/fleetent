## ADDED Requirements

### Requirement: 反抖动状态 session 级持久化、按次传入、跨 run 累计且无全局可变状态

自动压缩入口 SHALL 支持接收一份**按次传入**的反抖动状态（记录最近若干次自动压缩的节省率、自上次自动压缩以来的新增 turn 计数、自动压缩是否已熔断关闭）。该状态的作用域 SHALL 为 **session 生命周期级**，并 MUST **按 `session_id` 持久化于 `users.db`**（复用 session 元数据 sqlite 持久化家），由调用方在 run 边界 load/save。该状态 MUST NOT 以模块级可变全局形式持有，也 MUST NOT 写入 session 的裸消息数组文件。turns 计数与节省率滑窗 MUST 随对话**跨多次 run（多条用户消息）累计**，不在单次 run 结束时清零（仅在真正执行一次自动压缩时归零 turns 计数）。压缩逻辑 MUST 可在测试中通过直接构造并注入状态、或通过隔离的 `DB_PATH` 读写而无需真实会话。未传入反抖动状态时，自动压缩 MUST 退化为不含反抖动门控的现状行为（与 AR12 一致）。

#### Scenario: 不传状态时行为与 AR12 一致
- **WHEN** 调用自动压缩入口但不传入反抖动状态
- **THEN** 行为与 AR12 双阈值现状完全一致（越过 `Tmax` 即压缩、否则原样返回），不施加任何反抖动门控

#### Scenario: 传入状态被读取并返回更新后的状态
- **WHEN** 调用自动压缩入口并传入反抖动状态
- **THEN** 按该状态执行反抖动门控，并返回更新后的反抖动状态（不就地改写传入对象），供下次调用传回

#### Scenario: 反抖动状态按 session_id 持久化于 users.db 并跨 run 还原
- **WHEN** 一个 session 在某次 run 中更新了反抖动状态并写回 `users.db`，随后该 session 在下一次 run 开始时按 `session_id` 读取
- **THEN** 读回的反抖动状态与写入时一致（节省率滑窗、turns 计数、熔断标志），且 session 的裸消息数组文件不因此承载任何附加状态

### Requirement: 连续低节省熔断关闭自动压缩并告警

当连续 `flap_window`（默认 3）次自动压缩的节省率均低于 `min_savings_ratio`（默认 0.10）时，系统 SHALL 关闭该会话的自动压缩并记录一次结构化告警（提示扩大 context 上限或拆分任务）。节省率 MUST 定义为 `(压缩前估算 token − 压缩后估算 token) / 压缩前估算 token`（压缩前估算 token 不为正时记为 0）。仅**自动**压缩的节省率计入熔断统计；手动与上下文过长入口的压缩 MUST NOT 计入。告警 MUST NOT 以抛异常方式中断主循环，但 MUST NOT 被静默吞掉（须记录）。

#### Scenario: 连续 3 次低节省触发熔断
- **WHEN** 连续 3 次自动压缩的节省率均低于 0.10
- **THEN** 该会话自动压缩被关闭（状态标记为已熔断），并记录一次结构化告警

#### Scenario: 跨多次 run（多条用户消息）累计连续低节省触发熔断
- **WHEN** 同一 session 在多次 run（处理多条用户消息）中各发生一次低节省自动压缩，状态在 run 边界经 `users.db` 持久化与还原，累计达到连续 3 次节省率均低于 0.10
- **THEN** 该 session 自动压缩被关闭并记录一次结构化告警，证明熔断统计跨 run 累计、不因单次 run 结束而重置

#### Scenario: 中途一次达标打断连续性
- **WHEN** 三次自动压缩中有一次节省率达到或超过 `min_savings_ratio`
- **THEN** 连续低节省计数被打断，不触发熔断，自动压缩保持开启

#### Scenario: 熔断后自动路径原样返回
- **WHEN** 自动压缩已被熔断关闭，再次以自动路径调用且估算 token 越过 `Tmax`
- **THEN** 消息原样返回、不调用 LLM 摘要，不再执行自动压缩

### Requirement: 手动与上下文过长入口豁免反抖动门控

手动强制压缩（`/compact` 语义）与「LLM 报上下文过长」压缩入口 SHALL NOT 受熔断与最小间隔门控约束：即使自动压缩已被熔断关闭、或处于最小间隔窗口内，这两个入口 MUST 仍执行压缩并回落到 `Tretained` 目标线。这两个入口的节省率 MUST NOT 计入熔断统计。

#### Scenario: 熔断后手动仍可压缩
- **WHEN** 自动压缩已被熔断关闭，调用方请求手动强制压缩
- **THEN** 仍执行压缩并回落到 `Tretained` 目标线附近或以下，且本次不计入熔断统计

#### Scenario: 上下文过长入口不受熔断与窗口约束
- **WHEN** 自动压缩已被熔断关闭或处于最小间隔窗口内，调用方因 LLM 报上下文过长而请求压缩
- **THEN** 仍执行压缩并回落到 `Tretained` 目标线，返回压缩后的消息序列供重试

### Requirement: 最小压缩间隔滞后窗口

两次自动压缩之间 SHALL 保持至少 `min_interval_turns`（默认 1）个新增 turn 的滞后窗口。在窗口未满时，自动压缩入口即便估算 token 越过 `Tmax` 也 MUST 跳过本次自动压缩（消息原样返回、不调用 LLM）。一旦真正执行自动压缩，新增 turn 计数 MUST 归零。该窗口 MUST NOT 约束上下文过长入口（正确性兜底）。

#### Scenario: 窗口未满跳过自动压缩
- **WHEN** 距上次自动压缩的新增 turn 数小于 `min_interval_turns`，且当前估算 token 越过 `Tmax`
- **THEN** 跳过本次自动压缩，消息原样返回、不调用 LLM

#### Scenario: 窗口满足后正常压缩并归零计数
- **WHEN** 距上次自动压缩的新增 turn 数达到 `min_interval_turns` 且估算 token 越过 `Tmax`
- **THEN** 执行自动压缩，压缩后新增 turn 计数归零

### Requirement: 反抖动阈值可配置与注入

`flap_window`、`min_savings_ratio`、`min_interval_turns` MUST 支持部署级配置（`Settings` 的 env 字段）并支持通过注入的配置覆盖默认值。反抖动逻辑 MUST NOT 依赖全局可变状态，阈值 MUST 可在测试中通过传入配置注入而无需实例化真实 `Settings`。默认值 SHALL 为 `flap_window=3`、`min_savings_ratio=0.10`、`min_interval_turns=1`。

#### Scenario: 配置注入覆盖默认阈值
- **WHEN** 调用自动压缩时传入自定义的 `flap_window` / `min_savings_ratio` / `min_interval_turns`
- **THEN** 反抖动门控按注入的阈值判定熔断与最小间隔，而非默认值
