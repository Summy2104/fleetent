## ADDED Requirements

### Requirement: Materialize 将全局 disabled skills 写入 agent.yaml 的 disabled_skills

由于 agent 运行时只读 `agent.yaml`、从不访问 platform DB，平台的全局 skill disable 决策（`skill_admin_state.global_enabled=0`）SHALL 在 materialize 时被写入 `AgentFile.disabled_skills`。`agent_file_from_store()` SHALL 读取 `skill_admin_store.list_states()`，把所有 `global_enabled=0` 的 `skill_name` 汇集到 `disabled_skills`。

当 `skill_admin_state` 表不存在（旧库）时，materialize SHALL 安全回退到空 `disabled_skills`，不抛异常。

#### Scenario: 全局 disabled skill 写入 disabled_skills

- **WHEN** skill "crm-ops" 在 `skill_admin_state` 中 `global_enabled=0`，对任一 agent 触发 materialize
- **THEN** 产出的 agent.yaml 中 `disabled_skills` 包含 "crm-ops"

#### Scenario: 全局 enabled skill 不出现在 disabled_skills

- **WHEN** skill "jira" 在 `skill_admin_state` 中 `global_enabled=1`，触发 materialize
- **THEN** 产出的 agent.yaml 中 `disabled_skills` 不包含 "jira"

#### Scenario: 表缺失时安全回退

- **WHEN** `skill_admin_state` 表不存在，触发 materialize
- **THEN** materialize 正常完成，`disabled_skills` 为空列表，不抛异常
