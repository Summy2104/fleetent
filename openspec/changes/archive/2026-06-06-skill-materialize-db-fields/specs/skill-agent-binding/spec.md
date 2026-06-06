## ADDED Requirements

### Requirement: Materialize 将 agent_skills 绑定写入 agent.yaml 的 allowed_skills

由于 agent 运行时只读 `agent.yaml`、从不访问 platform DB，`agent_skills` 绑定矩阵 SHALL 在 materialize 时被转换为 `AgentFile.allowed_skills`。`agent_file_from_store()` SHALL 用 `has_any_binding(str(agent.id))` 判定该 agent 是否有绑定行：

- 有绑定行：`allowed_skills` SHALL 恰好为 `enabled_skill_names(str(agent.id))` 的内容（enabled=1 子集），即使该集合为空（表示该 agent 被显式收窄到无 skill）
- 无绑定行：`allowed_skills` SHALL 回退到 authored 的 `agent.allowed_skills`

#### Scenario: 有绑定时 allowed_skills 取 enabled 子集

- **WHEN** agent "support-bot" 在 `agent_skills` 中有 `(support-bot, crm-ops, enabled=1)` 和 `(support-bot, billing, enabled=0)`，触发 materialize
- **THEN** 产出的 agent.yaml 中 `allowed_skills` 恰好为 `["crm-ops"]`

#### Scenario: 绑定全部关闭时 allowed_skills 为空

- **WHEN** agent "support-bot" 在 `agent_skills` 中所有行的 `enabled` 均为 0，触发 materialize
- **THEN** 产出的 agent.yaml 中 `allowed_skills` 为空列表（catalog 收窄到无 skill）
- **AND** 不回退到 authored 的 allowed_skills

#### Scenario: 无绑定时回退 authored 值

- **WHEN** agent "support-bot" 在 `agent_skills` 中没有任何行，且其 authored `allowed_skills` 为 `["jira"]`，触发 materialize
- **THEN** 产出的 agent.yaml 中 `allowed_skills` 为 `["jira"]`
