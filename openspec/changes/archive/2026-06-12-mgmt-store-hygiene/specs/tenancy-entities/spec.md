# tenancy-entities Delta

## ADDED Requirements

### Requirement: agents 归属一致性
`agents.team_id` 非空时，该 team 的 `teams.tenant_id` **MUST** 与 `agents.tenant_id` 一致。store 写入路径（`create_agent` / `update_agent_tenancy`）**MUST** 在写入前强制此校验，不一致时拒绝并返回可诊断错误（指明 agent、team 及两侧 tenant）。此校验是物理路由正确性的护栏：路由主体取自 `agents.tenant_id`，team 与 tenant 矛盾会把该 agent 的 KB / 共享记忆解析到错误租户的库文件。

#### Scenario: 创建时拒绝跨租户 team
- **WHEN** `create_agent` 传入 `tenant_id=T1` 且 `team_id` 指向 `tenant_id=T2` 的 team
- **THEN** 创建被拒绝，错误信息指明归属不一致，`agents` 表无新行

#### Scenario: 更新时拒绝跨租户 team
- **WHEN** `update_agent_tenancy` 试图把 agent 改为 `tenant_id=T1` + 属于 `T2` 的 `team_id`
- **THEN** 更新被拒绝，原行保持不变

#### Scenario: 无 team 的 agent 不受影响
- **WHEN** `create_agent` / `update_agent_tenancy` 的 `team_id` 为空
- **THEN** 仅按 `tenant_id` 写入，不触发 team 一致性校验

#### Scenario: 存量数据一致性审计
- **WHEN** 对管理库现存全量 `agents` 行执行一致性审计（team_id 非空者 JOIN teams 比对 tenant）
- **THEN** 无不一致行
