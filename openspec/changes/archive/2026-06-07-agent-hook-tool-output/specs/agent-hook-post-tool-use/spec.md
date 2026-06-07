## ADDED Requirements

### Requirement: post_tool_use 工具结果变换与观测

当 hooks 启用且注册了 `post_tool_use` hook 时，agent loop SHALL 在工具**实际执行完成后**（`run` 与 `run_stream` 两路，仅对真实执行的工具，不含 pre_tool_use deny 产生的 placeholder）将工具结果 `dispatch("post_tool_use", ctx{tool_name, tool_args, tool_result, failed})`，并将 `modified_content` 替换进追加给 LLM 的 tool message content。未启用或无注册时 MUST 零行为变化。

#### Scenario: hook 改写工具结果
- **WHEN** `post_tool_use` hook 对某工具结果返回 `modified_content`
- **THEN** LLM 收到的 tool message content 为改写后的内容（脱敏/截断/重写）

#### Scenario: hook 仅做副作用观测
- **WHEN** `post_tool_use` hook 返回 `None`
- **THEN** 工具结果原样追加，流程无变化

#### Scenario: placeholder 不触发 hook
- **WHEN** 工具因 pre_tool_use deny / 审批拒绝未实际执行（placeholder slot）
- **THEN** `post_tool_use` hook 不被触发

#### Scenario: 未启用时零变化
- **WHEN** hooks 未启用或无 `post_tool_use` 注册
- **THEN** 工具结果处理与未引入本能力时完全一致
