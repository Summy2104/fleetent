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

主循环 SHALL 跟踪迭代轮数，并将其作为两维预算的「步数」维度纳入预算判定；当轮数达到配置的步数上限时，预算判定 MUST 认定预算耗尽，并经 Grace Call 收尾后以 `budget_exceeded` 原因终止当次任务（而非旧的硬切断 `max_turns` 收尾）。`StopReason.max_turns` 枚举成员 MUST 保留以兼容既有引用与历史 trace，但主循环 MUST NOT 再以 `max_turns` 作为步数维度命中时的终止原因码——步数维度命中由预算判定统一产出 `budget_exceeded`（触发维度记为步数）。该上限 MUST 可通过参数注入或配置覆盖默认值。

#### Scenario: 达到步数上限经 Grace Call 终止并产出 budget_exceeded
- **WHEN** 主循环迭代轮数达到步数上限且 LLM 仍在请求工具
- **THEN** 预算判定认定预算耗尽，主循环发起 Grace Call 生成进展总结后以 `budget_exceeded` 原因（触发维度为步数）终止，不再发起新的工具循环，且不以 `max_turns` 作为该次终止的原因码

#### Scenario: 未达上限时不受影响
- **WHEN** 迭代轮数未达步数上限且其它预算维度未耗尽
- **THEN** 预算判定不触发终止

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

### Requirement: 异常终止不返回空回复（给出用户可见状态）

当主循环以**异常原因**终止(`loop_detected` / `consecutive_failures` / `approval_rejected` / `cancelled`)且当前已有回复(去空白后)为空时,主循环 SHALL 返回一条**用户可见的状态回复**,说明任务已停止及其原因;对 `loop_detected` 与 `consecutive_failures`,在可得时 SHALL 附上**最后一条工具反馈/错误**(messages 中最后一条 tool 结果内容,归一化并截断)。主循环 MUST NOT 在这些异常终止下返回空回复(否则下游空回复守卫会跳过投递,导致用户静默)。

状态回复 SHALL 由确定性文本合成,MUST NOT 为此再发起一次模型调用。当已有回复非空时,既有「返回当前已有回复」语义不变(不替换)。`normal`(正常完成)、`budget_exceeded`(已有 Grace Call 兜底)、`awaiting_approval`(已发出审批提示、非终止)、`mcp_strict_unavailable`(已在入口返回明确错误)不受影响。流式(`run_stream`)与非流式(`run`)两条路径行为一致;流式在替换为状态回复时 SHALL 补发一条文本增量,使其进入最终输出。

#### Scenario: 循环检测终止且回复为空时返回状态与最后错误
- **WHEN** 主循环因 `loop_detected` 终止,且最后一条 assistant 文本为空,messages 中最后一条工具反馈为「需要 slackUserId 来定位用户」
- **THEN** 返回的回复非空,包含「已停止/重复调用未取得进展」的说明,并附上该工具反馈,提示用户换方式或补充信息

#### Scenario: 连续失败终止附最后错误
- **WHEN** 主循环因 `consecutive_failures` 终止且回复为空
- **THEN** 返回非空回复,说明连续工具失败已停止,并附最后一条工具错误

#### Scenario: 取消 / 审批拒绝给出说明
- **WHEN** 主循环因 `cancelled` 或 `approval_rejected` 终止且回复为空
- **THEN** 分别返回「任务已取消」/「操作未获批准，已取消」的用户可见说明（不附工具错误）

#### Scenario: 正常完成不受影响
- **WHEN** 主循环 `normal` 完成,或异常终止但已有非空回复
- **THEN** 返回原有回复,不替换、不附加状态文案

#### Scenario: 预算耗尽仍走 Grace Call
- **WHEN** 主循环因 `budget_exceeded` 终止
- **THEN** 仍由既有 Grace Call 产出总结回复,本要求不介入(不返回状态文案占位)
