# tenancy-entities Delta

## ADDED Requirements

### Requirement: 归属与审批人 FK 的删除语义
租户归属与审批人外键 SHALL 声明明确且统一的 `ON DELETE` 行为（消除现状 fresh 库 RESTRICT / legacy 库 NO ACTION 的分叉，及一批裸 NO ACTION）：
- `users.tenant_id` → `tenants`、`agents.tenant_id` → `tenants`、`agents.team_id` → `teams`、`teams.tenant_id` → `tenants`：**ON DELETE RESTRICT**——父主体/团队仍挂着子实体时拒绝删除，强制先迁移/清理，绝不静默误删数据。
- `tenants.approver_user_id` → `users`、`teams.approver_user_id` → `users`：**ON DELETE SET NULL**——审批人用户被删则把该列置空（列本就可空，由审批解析链 fallback / default-closed 处理），不阻塞删用户、不波及主体本身。

约束变更只动 FK 的 `ON DELETE` 子句，不改列、不改值、不破坏既有子表 CASCADE（agent 删除仍级联清理其绑定）。

#### Scenario: 删带子实体的 tenant 被 RESTRICT 拒绝
- **WHEN** 删除一个仍有 users / agents / teams 归属的 tenant
- **THEN** 删除被 FK RESTRICT 拒绝，tenant 行与全部子实体保持不变

#### Scenario: 删被 agent 引用的 team 被 RESTRICT 拒绝
- **WHEN** 删除一个仍被某 agent（`agents.team_id`）引用的 team
- **THEN** 删除被 FK RESTRICT 拒绝，team 行保持不变

#### Scenario: 删审批人用户置空 approver_user_id
- **WHEN** 删除一个被某 tenant / team 设为 `approver_user_id` 的 user
- **THEN** 该 tenant / team 的 `approver_user_id` 被 SET NULL，删用户成功，主体本身保留

#### Scenario: fresh 与 legacy 库删除语义一致
- **WHEN** 在全新建库与从旧库升级两条路径上检查 `users.tenant_id` 的 FK
- **THEN** 两者均为 ON DELETE RESTRICT（不再分叉）
