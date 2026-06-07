## ADDED Requirements

### Requirement: pre_compact 压缩前注入与观测

当 hooks 启用且注册了 `pre_compact` hook 时，agent loop SHALL 在每次上下文压缩前 dispatch `"pre_compact"` ctx`{message_count}`。`inject_context`→在压缩输入 messages 末尾追加内容（运维方可注入"必保留"标记或策略）。未启用时 MUST 零行为变化。

#### Scenario: hook 注入必保留内容
- **WHEN** `pre_compact` hook 返回 `inject_context`
- **THEN** 该内容追加到待压缩 messages，压缩过程可见

#### Scenario: 未启用时零变化
- **WHEN** hooks 未启用
- **THEN** 压缩行为与未引入本能力时完全一致

### Requirement: post_compact 压缩后观测

当 hooks 启用且注册了 `post_compact` hook 时，agent loop SHALL 在上下文压缩完成后 dispatch `"post_compact"` ctx`{messages_before, messages_after}`；纯观测，返回值不影响流程。

#### Scenario: hook 观测压缩结果
- **WHEN** `post_compact` hook 注册并 hooks 启用
- **THEN** 每次压缩后 hook 被调用，payload 含压缩前后消息数
