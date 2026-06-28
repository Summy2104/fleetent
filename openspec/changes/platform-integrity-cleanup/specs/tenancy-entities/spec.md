# tenancy-entities

## MODIFIED Requirements

### Requirement: agents 归属一致性
`agents.team_id` 非空时，该 team 的 `teams.tenant_id` **MUST** 与 `agents.tenant_id` 一致。此一致性 **MUST** 由两层强制：
1. **store 写入路径**（`create_agent` / `update_agent_tenancy`）在写入前校验，不一致时拒绝并返回可诊断错误（指明 agent、team 及两侧 tenant）。
2. **DB 级复合外键**：`teams` 声明 `UNIQUE(id, tenant_id)`，`agents.team_id` 经复合外键 `(team_id, tenant_id) → teams(id, tenant_id)`（`ON DELETE RESTRICT`）强制——即便绕过 store 直写，DB 也拒绝跨租户引用。
此校验是物理路由正确性的护栏：路由主体取自 `agents.tenant_id`，team 与 tenant 矛盾会把该 agent 的 KB / 共享记忆解析到错误租户的库文件。

#### Scenario: 创建时拒绝跨租户 team
- **WHEN** `create_agent` 传入 `tenant_id=T1` 且 `team_id` 指向 `tenant_id=T2` 的 team
- **THEN** 创建被拒绝，错误信息指明归属不一致，`agents` 表无新行

#### Scenario: 更新时拒绝跨租户 team
- **WHEN** `update_agent_tenancy` 试图把 agent 改为 `tenant_id=T1` + 属于 `T2` 的 `team_id`
- **THEN** 更新被拒绝，原行保持不变

#### Scenario: DB 复合外键兜底拒绝跨租户引用
- **WHEN** 绕过 store 校验直接向 `agents` 写入 `tenant_id=T1` + 属于 `T2` 的 `team_id`
- **THEN** 复合外键约束拒绝该写入（DB 层报错），不产生跨租户引用行

#### Scenario: 无 team 的 agent 不受影响
- **WHEN** `create_agent` / `update_agent_tenancy` 的 `team_id` 为空
- **THEN** 仅按 `tenant_id` 写入，不触发 team 一致性校验

#### Scenario: 存量数据一致性审计
- **WHEN** 对管理库现存全量 `agents` 行执行一致性审计（team_id 非空者 JOIN teams 比对 tenant）
- **THEN** 无不一致行
