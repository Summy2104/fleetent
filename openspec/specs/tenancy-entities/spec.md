# Spec: tenancy-entities

## Purpose

多租户基础实体层：`tenants`（主体）与 `teams`（团队）根实体，`users.tenant_id` 外键归属，两级审批人字段，以及将 `users` 表纳入 Alembic 管理的 schema 迁移。

---
## Requirements
### Requirement: tenant / team 根实体
系统 **MUST** 提供 `tenants`(主体)与 `teams`(团队)根实体,均以 uuid 字符串为主键。`teams.tenant_id` **MUST** 外键引用 `tenants`。两表 **MUST** 由 Alembic 迁移建立(管理库 alembic 权威),不走 store `_init_db`。

#### Scenario: 空库建出 tenant/team 表
- **WHEN** 对空库执行 `alembic upgrade head`
- **THEN** schema 含 `tenants`、`teams` 两表,`teams.tenant_id` 为外键指向 `tenants.id`

#### Scenario: 主体下建团队
- **WHEN** 在主体 T 下创建团队 "财务"
- **THEN** 该 team 行的 `tenant_id` = T,`id` 为新 uuid

### Requirement: default 主体与回填
迁移 **MUST** 创建一个 id=`"default"` 的 default 主体(对齐现有 `tenant_id` 列的默认值)。所有现有 `users` 的 `tenant_id` **MUST** 回填为 `"default"`;回填后 `users.tenant_id` **MUST** 置为 NOT NULL 且外键引用 `tenants`。现有 `agents`/`knowledge_*`/`traces`/`policies` 的 `tenant_id`(已为 `"default"`)**MUST** 升为外键引用 `tenants`;`agents.team_id`(可空)**MUST** 升为外键引用 `teams`。

#### Scenario: 现有用户回填 default 主体
- **WHEN** 迁移在已有用户的库上执行
- **THEN** 每个 user 的 `tenant_id` = `"default"`,且 default 主体行存在、`users.tenant_id` 为 NOT NULL 外键

#### Scenario: 现有 agent 的 tenant_id 升外键不丢值
- **WHEN** 某 agent 原 `tenant_id="default"`
- **THEN** 迁移后该值不变,且成为指向 default 主体的外键

### Requirement: users 归属主体、不连 team
`users` **MUST** 携带 `tenant_id`(归属一个主体);v1 **MUST NOT** 为 `users` 建立 team 关系(无 `users.team_id`、无 `team_members`)——用户的 team 当前无任何消费方。`teams` 可反向引用 user 作为审批人(见下),但 user 不记录自身所属 team。

#### Scenario: user 只有主体归属
- **WHEN** 创建一个新 user 并指定主体 T
- **THEN** user 行有 `tenant_id=T`,系统无 user↔team 成员记录

### Requirement: 两级审批人字段
`tenants` 与 `teams` **MUST** 各有一个可空的 `approver_user_id`(外键引用 `users`),作为审批人解析链的源:agent 归属 team 的审批人 → (无)主体的审批人 → (无)default-closed reject。本期只建字段;实际"materialize 进 agent.yaml `approval` 块"的解析在部署侧(见 target-architecture §6.5),不在本期实现运行时解析。

#### Scenario: 设置团队审批人
- **WHEN** admin 把用户 U 设为团队 "财务" 的审批人
- **THEN** 该 team 行 `approver_user_id=U`(U 须存在)

#### Scenario: 审批人可空
- **WHEN** 新建主体/团队未指定审批人
- **THEN** `approver_user_id` 为 NULL(解析时由上层 fallback / default-closed 处理)

### Requirement: 最小 provisioning(admin)
系统 **MUST** 提供管理员可用的最小 provisioning 入口，经**平台 HTTP API**（`/admin/tenancy/*`）：创建主体、创建团队、设置某 user 的 `tenant_id`、设置主体/团队的 `approver_user_id`。这些操作 **MUST** 受现有 admin 鉴权（session token）保护并写审计，**MUST NOT** 经绕过 server 直写管理库的 CLI 提供（见 module-boundaries「Admin CLI 直写管理库的边界」）。

#### Scenario: 建主体并分配用户
- **WHEN** admin 经 HTTP API 创建主体 "A主体" 并把用户 U 的 `tenant_id` 设为它
- **THEN** "A主体" 行存在，U 的 `tenant_id` 指向它，且操作被审计

#### Scenario: provisioning 无直写 CLI 路径
- **WHEN** 查看 `fleetent platform` 子命令
- **THEN** 不存在 create-tenant / create-team / set-user-tenant / set-approver 等直写管理库的命令；provisioning 仅经 HTTP API

### Requirement: users 纳入 alembic + 启动门
因需为 `users` 加外键列,本变更 **MUST** 将 `users` 表纳入 Alembic 管理(从 store `_init_db` 迁出);其后 `users` 的 schema **MUST** 仅由 alembic 维护。部署在使用前 **MUST** 先 `alembic upgrade head`(`users` 不再由 `_init_db` 自愈)。

#### Scenario: users schema 由 alembic 建
- **WHEN** 空库 `alembic upgrade head`
- **THEN** `users` 表(含 `tenant_id`)由 alembic 迁移建出,`user_store` 不再 `_init_db` 建 `users`

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

### Requirement: 归属与审批人 FK 的删除语义
租户归属与审批人外键 **MUST** 声明明确且统一的 `ON DELETE` 行为：
- `users.tenant_id` → `tenants`、`agents.tenant_id` → `tenants`、`agents.team_id` → `teams`、`teams.tenant_id` → `tenants`：**ON DELETE RESTRICT**
- `tenants.approver_user_id` → `users`、`teams.approver_user_id` → `users`：**ON DELETE SET NULL**

#### Scenario: 删带子实体的 tenant 被 RESTRICT 拒绝
- **WHEN** 删除一个仍有 users / agents / teams 归属的 tenant
- **THEN** 删除被 FK RESTRICT 拒绝，tenant 行与全部子实体保持不变

#### Scenario: 删被 agent 引用的 team 被 RESTRICT 拒绝
- **WHEN** 删除一个仍被某 agent（`agents.team_id`）引用的 team
- **THEN** 删除被 FK RESTRICT 拒绝，team 行保持不变

#### Scenario: 删审批人用户置空 approver_user_id
- **WHEN** 删除一个被某 tenant / team 设为 `approver_user_id` 的 user
- **THEN** 该 tenant / team 的 `approver_user_id` 被 SET NULL，删用户成功，主体本身保留

