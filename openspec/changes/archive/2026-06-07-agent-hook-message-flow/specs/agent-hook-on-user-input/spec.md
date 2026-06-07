## ADDED Requirements

### Requirement: on_user_input 用户输入拦截、改写与注入

当 hooks 启用且注册了 `on_user_input` hook 时，agent 系统 SHALL 在用户输入进入对话历史前（IM 路径：normalizer.route；HTTP 路径：run_stream 入口）`dispatch("on_user_input", ctx{content: user_text})`，并按结果处理：`deny`→拒绝该消息（IM 路径向用户回复提示；run_stream 路径 yield error 事件并返回）；`modified_content`→替换用户输入文本；`inject_context`→向本次 turn 追加额外上下文（企业政策、背景信息等）。未启用或无注册时 MUST 零行为变化。

#### Scenario: hook 拒绝用户消息
- **WHEN** `on_user_input` hook 对某消息返回 `deny`
- **THEN** IM 路径：向用户回复拒绝提示，消息不进入历史；HTTP 路径：yield error 事件并终止流

#### Scenario: hook 改写用户输入
- **WHEN** `on_user_input` hook 返回 `modified_content`
- **THEN** LLM 收到的用户消息为改写后的文本

#### Scenario: 未启用时零变化
- **WHEN** hooks 未启用或无 `on_user_input` 注册
- **THEN** 用户输入处理与未引入本能力时完全一致
