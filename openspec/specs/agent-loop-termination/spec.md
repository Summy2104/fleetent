# agent-loop-termination Specification

## Purpose
TBD - created by archiving change termination-framework. Update Purpose after archive.
## Requirements
### Requirement: 统一终止检查点

agent 主循环（`run()` 与 `run_stream()`）SHALL 在每轮 LLM 调用前评估一组终止策略；当任一策略判定应终止时，主循环 MUST 停止继续调用 LLM，并以已产生的内容作为最终回复返回。

#### Scenario: 未触发任何终止条件时正常迭代
- **WHEN** 主循环完成一轮工具调用且无终止策略判定终止
- **THEN** 主循环进入下一轮 LLM 调用，行为与现状一致

#### Scenario: 终止判定优先于继续迭代
- **WHEN** 某终止策略在新一轮 LLM 调用前判定应终止
- **THEN** 主循环不再发起该轮 LLM 调用，直接收尾并返回当前已有回复

### Requirement: 可扩展的终止策略注册表

终止框架 SHALL 提供一个策略注册机制，每个终止原因由一个独立的 checker 实现并注册到 `TerminationController`。新增终止原因 MUST 能通过新增 checker 并注册的方式接入，而不需要修改主循环已有的判定分支。

#### Scenario: 注册自定义终止策略
- **WHEN** 向 `TerminationController` 注册一个新的 checker
- **THEN** 该 checker 在主循环的每轮终止评估中被调用，无需改动 `agent_loop.py` 的循环体

#### Scenario: 预留扩展原因不影响本次行为
- **WHEN** 框架定义了 `loop_detected` / `budget_exceeded` / `cancelled` 等原因码但未注册对应 checker
- **THEN** 这些原因永不触发，主循环仅受已注册的 `max_turns` / `consecutive_failures` / `approval_rejected` 影响

### Requirement: max_turns 终止

主循环 SHALL 跟踪迭代轮数；当轮数达到配置的上限时，终止框架 MUST 以原因码 `max_turns` 终止当次任务。该上限 MUST 可通过参数注入或配置覆盖默认值。

#### Scenario: 达到迭代上限时停止
- **WHEN** 主循环迭代轮数达到 `max_turns` 上限且 LLM 仍在请求工具
- **THEN** 主循环以 `max_turns` 原因终止，返回当前已有回复，不再发起新的 LLM 调用

#### Scenario: 未达上限时不受影响
- **WHEN** 迭代轮数未达 `max_turns` 上限
- **THEN** `max_turns` 策略不触发终止

### Requirement: consecutive_failures 终止

主循环 SHALL 跟踪连续失败的工具调用次数；当连续失败次数达到配置阈值时，终止框架 MUST 以原因码 `consecutive_failures` 终止当次任务。一次成功的工具调用 MUST 将连续失败计数重置为零。该阈值 MUST 可注入/配置。

#### Scenario: 连续失败达到阈值时停止
- **WHEN** 工具调用连续失败次数达到配置阈值
- **THEN** 主循环以 `consecutive_failures` 原因终止，返回当前已有回复

#### Scenario: 成功调用重置失败计数
- **WHEN** 在连续失败若干次后出现一次成功的工具调用
- **THEN** 连续失败计数归零，需重新累计才可能触发 `consecutive_failures`

### Requirement: approval_rejected 终止

当高风险工具的人工审批被拒绝时，`run()` 路径 MUST 以原因码 `approval_rejected` 终止当次任务，而非将拒绝结果当作工具结果继续循环。被拒工具 MUST 仍写入一条占位 tool_result，以保证发给 LLM 的消息序列不出现「有 tool_call 无对应 tool_result」的残缺。

> 注：`run_stream()` 现状不执行审批拦截，故本要求当前仅约束 `run()` 路径。

#### Scenario: 审批被拒终止任务
- **WHEN** `run()` 中某高风险工具的审批结果为 reject（或审批超时按拒绝处理）
- **THEN** 主循环以 `approval_rejected` 原因终止，不再发起后续 LLM 调用

#### Scenario: 被拒工具保持消息契约完整
- **WHEN** 工具因审批被拒未执行
- **THEN** 该 tool_call 对应仍有一条占位 tool_result，消息序列对 LLM 合法

### Requirement: 终止原因码写入 trace

任务终止时，终止框架 SHALL 将终止原因码写入运行日志（trace）。正常结束（LLM 返回 `finish_reason != "tool_calls"`）MUST 记录为正常终止原因，而非失败原因。

#### Scenario: 强制终止记录原因码
- **WHEN** 任务因 `max_turns` / `consecutive_failures` / `approval_rejected` 被强制终止
- **THEN** 该次运行的 trace 记录中包含对应的终止原因码

#### Scenario: 正常结束记录正常原因
- **WHEN** LLM 返回 `finish_reason != "tool_calls"` 自然结束
- **THEN** trace 记录的终止原因为正常结束，不标记为失败

