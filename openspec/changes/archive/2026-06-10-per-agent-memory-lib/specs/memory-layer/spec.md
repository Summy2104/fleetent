## ADDED Requirements

### Requirement: 记忆隔离经 per-agent 物理库（移除 namespace 第二参）

user memory 的 agent 隔离 SHALL 由"每 agent 一个 `agent_state.db`"物理库提供，而非 `namespace` 区分。`vector_store.memory_namespace` SHALL 仅取 `user_id`（返回 `mem:{user_id}`），memory 的 `search` / `extract_and_update` 等操作 SHALL NOT 再带 `namespace` 第二参。user-scoping（按 `user_id` 限定）不变。

#### Scenario: memory_namespace 仅按 user_id

- **WHEN** 调用 `memory_namespace(user_id)`
- **THEN** 返回 `mem:{user_id}`，不接受/不要求 namespace 第二参

#### Scenario: memory 操作无 namespace 参

- **WHEN** 调用 memory 的 `search` / `extract_and_update`
- **THEN** 其签名不含 `namespace` 第二参；记忆按 `user_id` scope、按 per-agent 库隔离

#### Scenario: user-scoping 不变

- **WHEN** 在某 agent 库中检索某 user 的记忆
- **THEN** 仍只返回该 `user_id` 的记忆（user 维度 scope 保持）
