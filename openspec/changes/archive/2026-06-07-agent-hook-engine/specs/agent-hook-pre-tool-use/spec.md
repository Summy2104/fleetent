## ADDED Requirements

### Requirement: pre_tool_use 决策与改参组合既有准入

当 hooks 启用且注册了 `pre_tool_use` hook 时，agent loop SHALL 在工具分发**前**（`run` 与 `run_stream` 两路）`dispatch("pre_tool_use", ctx{tool_name, tool_args})`，并将结果**与既有准入（`allowed_tools` 白名单 + `permission_gate` 审批）组合**：`deny`→跳过该工具分发并把 `reason` 作为工具结果反馈模型；`ask`→强制走 `permission_gate` 审批（即使该工具非 medium/high 风险）；`modified_args`→用改写后的入参分发；`proceed`/`None`→按既有流程继续。MUST NOT 另起一个独立的工具准入决策点。未启用或无注册 hook 时 MUST 零行为变化。

#### Scenario: hook 拒绝工具调用
- **WHEN** `pre_tool_use` hook 对某工具返回 `deny`
- **THEN** 该工具不被分发，其 reason 作为结果反馈给模型，序列对 LLM 合法

#### Scenario: hook 改写工具入参
- **WHEN** `pre_tool_use` hook 返回 `modified_args`
- **THEN** 工具以改写后的入参执行

#### Scenario: hook 要求人工确认
- **WHEN** `pre_tool_use` hook 对一个低风险工具返回 `ask`
- **THEN** 该次调用被路由到 `permission_gate` 审批后再决定是否执行

#### Scenario: 未启用时零变化
- **WHEN** hooks 未启用或无 `pre_tool_use` 注册
- **THEN** 工具准入与未引入本能力时完全一致
