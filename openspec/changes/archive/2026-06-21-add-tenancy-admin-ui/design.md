## Context

C1 港域范式已坐实。Tenancy 是 **net-new UI**:legacy 无 tenancy tab(只有裸 `tenant_id` 输入框),无 parity 基线,按 `tenancy/admin_api` 能力建。后端:`/admin/tenancy` 提供 tenants/teams 列表与创建、用户到租户分配、审批人设置。

## Goals / Non-Goals

**Goals:** 运维在 SPA 管租户/团队(列表/创建)、把用户分配到租户、设审批人;TDD + MSW。
**Non-Goals:** 不改 tenancy 后端 API;不做租户级配额/计费等后端没有的东西;不动其它域。

## Decisions

**D1 · 照 agents 范式。** `features/tenancy/api.ts`:tenants/teams 的 query + create hooks、`useAssignUserTenant`、`useSetApprover`,mutation 后失效相关列表。`page.tsx`:租户列表 + 建、团队列表 + 建、用户归属分配、审批人设置。

**D2 · net-new 无 parity,以 API 能力为准。** 字段/操作严格按 `tenancy/admin_api` 实际端点与返回,不臆造配额/计费维度。

**D3 · routes.tsx 共享缝。** 注册 tenancy(import + NavLink + Route),不涉及 legacyLinks。`routes.test.tsx` 用 `within(nav)` scope。

## Risks / Trade-offs

- **[net-new 易过度设计]** → 严格按现有 API(tenants/teams/assign/approvers)建。
- **[多租户敏感操作]** → 创建/分配/审批人变更需清晰反馈;遵循 admin-only 写、viewer 只读。
- **[与同期前端域撞 routes.tsx]** → 合并由主会话串行做。
