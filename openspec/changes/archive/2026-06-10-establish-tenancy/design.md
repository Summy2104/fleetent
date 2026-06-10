## Context

§5.7 tenancy 决议:tenant=主体、强隔离。但 `tenant_id`/`team_id` 是裸列无根实体(§4-②),`users` 无组织归属。本变更立**逻辑** tenancy 实体于管理库,使系统租户感知 + 引用完整性 + 审批人链(§6.5)的源就位。**物理 per-tenant 分区是 #3**,不在本期。

身份模型背景见 `target-architecture-proposal.md §6` 与 [[identity-auth-model]]:Principal=`{user_id,tenant_id}`;`users.tenant_id`(本期加)是 #4 principal.tenant_id 的源;审批人=agent 归属 team/主体的 approver。

## Goals / Non-Goals

**Goals**:立 `tenants`/`teams` + `users.tenant_id` + 两级 `approver_user_id` + default 主体回填 + 最小 provisioning;把 `users` 纳入 alembic。

**Non-Goals(明确排除)**:
- 物理 per-tenant 库分区(#3)。
- 全查询 tenant 强制过滤(由 #3 物理隔离负责;本期只立 FK,不重写各 store 查询)。
- Identity 端口 / principal 运行时解析(#4)。
- 审批人"materialize 进 agent.yaml + 运行时解析"(部署侧/后续;本期只建字段)。
- 其余管理表(api_keys/audit_log/im_connectors/im_channel_allowlist)收编 alembic(#2)。
- `users.team_id` / `team_members`(v1 用户的 team 无消费方)。

## Decisions

**D1:新表 uuid 字符串 id,default 主体 id=`"default"`。** 对齐主流(users 等用 uuid str)+ 现有 `tenant_id` 列值(`"default"`)。不用 INTEGER 自增/复合键(id 风格全局统一是 §4-③ 另题)。

**D2:`users` 纳入 alembic(本期为它做)。** 加外键列必须经统一迁移;顺带把 `users` 从 `_init_db` 迁到 alembic(#2 的同类工作,但 users 这一张在本期完成,因为 tenant_id 依赖它)。其余管理表留 #2。

**D3:逻辑优先,不动物理 + 不重写查询。** 只建实体 + FK + 回填;租户的物理隔离与查询强制留 #3。诚实代价见 Risks。

**D4:approver 在 org 表上、可空;不在 team_members(无此表)。** team 知道自己的审批人;user 不记自己的 team。

## Risks / Trade-offs

- **[#2.5→#3 隔离裸奔(承重)]** → 含 provisioning 能建 A/B,但物理隔离在 #3;之间 A/B 仅逻辑(列)分隔,漏过滤即泄漏。**缓解**:物理隔离就绪前勿灌真敏感数据,或 #3 紧跟 #2.5;在 proposal/部署文档显式标注。
- **[users 入 alembic 的启动门]** → 失去 `_init_db` 自愈,部署须先 `upgrade head`;migrate 须幂等、可在已有数据库上安全跑(回填只补空)。
- **[迁移可逆]** → downgrade 须能去 FK/列/表并保留数据;空库 upgrade→downgrade→upgrade 往返通过。
- **[现有 tenant_id 值非 "default"?]** → 迁移前核查现有 `agents/KB/traces.tenant_id` 是否都为 `"default"`;若有他值,迁移须为这些值也建对应 tenant 行(或归一),避免 FK 失败。
