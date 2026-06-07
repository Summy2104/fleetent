## ADDED Requirements

### Requirement: session_start / session_end 会话起止钩子点

当 hooks 启用且注册了 `session_start`/`session_end` hook 时，`normalizer.route` SHALL 在：
- 会话锁内、history 加载后、用户消息追加前 dispatch `"session_start"` ctx`{session_id, user_id, message_count}`；`inject_context`→在 history 末尾追加初始化上下文。
- `run()` 返回后、session 保存前 dispatch `"session_end"` ctx`{session_id, user_id, reply}`；纯观测。

未启用时 MUST 零行为变化。

#### Scenario: session_start 注入初始化上下文
- **WHEN** `session_start` hook 返回 `inject_context`
- **THEN** 追加到 history，LLM 在本 turn 可见

#### Scenario: session_end 观测 reply
- **WHEN** `session_end` hook 注册并 hooks 启用
- **THEN** 每轮会话结束后被调用，payload 含 reply
