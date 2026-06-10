## Why

多主体(法人实体)需**强隔离**(§5.7 tenancy 决议:A/B 主体财务数据互不可见)。但当前 `tenant_id`/`team_id` 是**裸列、无根实体**(§4-② 幻影),`users` 连组织归属都没有。本变更立 **逻辑 tenancy 实体**(管理库内),使系统**租户感知** + 有引用完整性 + 审批人解析链(§6.5)可用。

**物理 per-tenant 库分区留 #3**;本期只把实体/FK/归属/审批人在**单管理库**内立起来(逻辑先行、物理后补)。

## What Changes

- 新建 **`tenants`**(=主体)、**`teams`**,uuid 字符串 id;**default 主体 id=`"default"`**(对齐现有列值)。
- **`tenants.approver_user_id` / `teams.approver_user_id`**(可空)——审批人解析链(agent 归属 team → tenant → reject)的源。
- **`users` 加 `tenant_id`**→tenants(回填 `"default"`、置 NOT NULL);**users 不连 team**(v1 无 `team_members`——全库无处读用户的 team)。
- 现有 `agents`/`KB`/`traces`/`policies` 的 `tenant_id`(已=`"default"`)升 **FK→tenants**;`agents.team_id`(可空)升 **FK→teams**。
- 把 **`users` 纳入 alembic**(它本是 store-self-built;加 FK 列须经统一迁移),并加 default-tenant 创建 + 回填迁移。
- 最小 **provisioning**(admin CLI/API):create tenant / create team / 设 user.tenant_id / 设 tenant|team 的 approver。

> **不做**:物理 per-tenant 库分区(#3);全查询 tenant 强制过滤(由 #3 物理隔离负责);Identity 端口 / principal(#4);其余管理表(api_keys/audit_log/im_connectors/im_channel_allowlist)收编 alembic(#2)。

## Capabilities

### New Capabilities
- `tenancy-entities`: 主体(tenant)/团队(team)根实体 + `users.tenant_id` + 两级 `approver_user_id` + default 主体回填 + 最小 provisioning。

### Modified Capabilities
（无；`agent-data-isolation` 是 per-agent 运行时**数据目录**隔离,与本期 org 实体正交,不动。）

## Impact

- **迁移**:新 alembic 迁移建 `tenants`/`teams`、加 `users.tenant_id`+FK、加两个 `approver_user_id`、建 default 主体、回填 `users.tenant_id="default"`、把现有 `agents/KB/traces.tenant_id` 与 `agents.team_id` 升为 FK。**`users` 纳入 alembic**。
- **代码**:`user_store`(`User` 加 `tenant_id`、CRUD、`_FULL_COLS`);新 tenancy store(tenants/teams CRUD)+ admin API/CLI(provisioning);`agent_store` 的 team_id/tenant_id 仍存在(值不变,仅升 FK)。
- **启动门**:`users` 入 alembic 后,部署须先 `alembic upgrade head`(失去 `_init_db` 自愈)——本期为 users 立这道门。
- **⚠️ 安全(承重)**:本期含 provisioning 能建 A/B 主体,但**物理隔离在 #3**——`#2.5→#3` 之间 A/B 仅**逻辑(列)分隔**,某查询漏 tenant 过滤即可能 A↔B 泄漏。故**物理隔离(#3)就绪前勿往 A/B 灌真敏感数据**(或 #3 紧跟 #2.5)。
