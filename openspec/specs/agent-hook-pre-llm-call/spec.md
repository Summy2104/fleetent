## ADDED Requirements

### Requirement: pre_llm_call LLM 调用前注入与观测

当 hooks 启用且注册了 `pre_llm_call` hook 时，agent loop SHALL 在每轮 LLM 调用前（compress/sanitize 后、client.chat.completions.create 前，`run` 与 `run_stream` 两路）`dispatch("pre_llm_call", ctx{message_count: len(messages)})`，并将 `inject_context` 追加到本次发送给 LLM 的 messages（`{"role": "user", "content": inject_context}`）。纯观测返回 None 无副作用。未启用或无注册时 MUST 零行为变化。

#### Scenario: hook 注入上下文
- **WHEN** `pre_llm_call` hook 返回 `inject_context`
- **THEN** 追加 user 消息到 messages，LLM 在本次调用时可见该上下文

#### Scenario: hook 仅观测
- **WHEN** `pre_llm_call` hook 返回 `None`
- **THEN** messages 无变化，LLM 调用按正常流程进行

#### Scenario: 未启用时零变化
- **WHEN** hooks 未启用或无 `pre_llm_call` 注册
- **THEN** LLM 调用与未引入本能力时完全一致
