## ADDED Requirements

### Requirement: Skill 写操作触发受影响 agent 的 re-materialize

由于 agent 运行时只读 agent.yaml、不访问 platform DB，skill 管理的写操作 SHALL 在写 DB 后触发受影响 agent 的 re-materialize，把最新决策落到各 agent 的 agent.yaml。触发是 best-effort：单个 agent 的 re-materialize 失败 SHALL 被记录但不阻断接口响应或其余 agent 的刷新。

- 全局 enable/disable（`POST /admin/skills/{name}/enable|disable`）影响所有 agent 的 `disabled_skills`，SHALL 触发全量 re-materialize
- per-agent 绑定（`PUT /admin/skills/{name}/agents/{agent_id}`）只影响该 agent 的 `allowed_skills`，SHALL 只 re-materialize 该 agent

#### Scenario: 全局 disable 触发全量 re-materialize

- **WHEN** admin 调用 `POST /admin/skills/crm-ops/disable`
- **THEN** DB 中该 skill 的 `global_enabled` 置为 0，写审计日志
- **AND** 所有 authored agent 的 agent.yaml 被重新导出（best-effort）

#### Scenario: per-agent 绑定只 re-materialize 对应 agent

- **WHEN** admin 调用 `PUT /admin/skills/crm-ops/agents/{id}` 设置某 agent 的绑定
- **THEN** 该 agent 的 agent.yaml 被重新导出
- **AND** 其他 agent 的 agent.yaml 不被触碰

#### Scenario: 单个 agent re-materialize 失败不阻断接口

- **WHEN** 全量 re-materialize 过程中某个 agent 导出失败（如缺 provider 配置）
- **THEN** 该失败被记录为结构化告警，接口仍返回成功，其余 agent 正常刷新
