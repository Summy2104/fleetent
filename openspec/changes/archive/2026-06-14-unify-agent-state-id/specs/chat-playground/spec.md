# chat-playground Delta

## ADDED Requirements

### Requirement: session_meta 的 agent 引用以 agents.id 为键
`session_meta`（playground / chat admin 会话治理元数据）对 agent 的引用 SHALL 用 `agent_id`（INTEGER，= `agents.id`）+ FK→`agents.id` ON DELETE CASCADE，MUST NOT 用 agent name。`user_id`（用户身份）列**不在本约束范围、不变**。playground 隔离、接管、置顶、保留等治理行为不变；HTTP 按 `{name}` 寻址时 MUST 先解析 name→`agents.id`。

#### Scenario: session_meta agent 引用为整数 agent_id + FK
- **WHEN** 管理库迁移运行到最新版本
- **THEN** `session_meta` 以 `agent_id`（INTEGER）引用 agent、存在 FK→`agents.id` ON DELETE CASCADE，且无 agent name 列

#### Scenario: agent 删除级联清理其会话治理元数据
- **WHEN** 一个 agent 被删除
- **THEN** 其 `session_meta` 行随 FK ON DELETE CASCADE 一并删除，不留孤儿

#### Scenario: user_id 不受影响
- **WHEN** 本迁移运行
- **THEN** `session_meta.user_id` 列与语义保持不变（用户身份不在本次 agent 身份规整范围）
