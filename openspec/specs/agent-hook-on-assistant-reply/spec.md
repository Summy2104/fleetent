## ADDED Requirements

### Requirement: on_assistant_reply LLM 回复改写与观测

当 hooks 启用且注册了 `on_assistant_reply` hook 时，agent loop SHALL 在 LLM 返回 assistant 文本内容后（仅对有文本内容的 turn，tool_calls-only turn 跳过）、消息追加进 messages 前（`run` 路径）或在最终 reply 定稿后 break 前（`run_stream` 路径），`dispatch("on_assistant_reply", ctx{content: assistant_content})`，并将 `modified_content` 替换进 messages 或 reply。未启用或无注册时 MUST 零行为变化。

#### Scenario: hook 改写 assistant 回复内容
- **WHEN** `on_assistant_reply` hook 返回 `modified_content`
- **THEN** run() 路径：追加进 messages 的 assistant content 为改写后的值；run_stream() 路径：reply 为改写后的值（后续 output_transform + done 事件使用改写值）

#### Scenario: hook 仅观测
- **WHEN** `on_assistant_reply` hook 返回 `None`
- **THEN** assistant 消息原样处理，流程无变化

#### Scenario: tool_calls turn 不触发
- **WHEN** LLM 返回的是 tool_calls（content 为 None/空）
- **THEN** on_assistant_reply hook 不被触发

#### Scenario: 未启用时零变化
- **WHEN** hooks 未启用或无 `on_assistant_reply` 注册
- **THEN** LLM 回复处理与未引入本能力时完全一致
