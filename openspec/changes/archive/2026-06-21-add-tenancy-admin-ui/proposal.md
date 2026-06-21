## Why

多租户/团队 provisioning 后端齐全(`tenancy/admin_api`),但**全程无 UI**——legacy 只有个裸 `tenant_id` 输入框,租户/团队/审批人都只能 CLI/API 管(标准 2 的 MISSING 项)。本切片在新 SPA 加原生 Tenancy 域(net-new),让运维在页面上管租户、团队、用户归属与审批人。

## What Changes

- 新增 `features/tenancy/`(`api.ts` + `page.tsx` + `page.test.tsx`),照 C1 agents 范式(TanStack Query + MSW + TDD)。
- 覆盖既有 admin API(`/admin/tenancy`):租户 列表 `GET /tenants` / 建 `POST /tenants`;团队 列表 `GET /teams` / 建 `POST /teams`;把用户分配到租户 `POST /users/{id}/tenant`;设置审批人 `PATCH /approvers/{entity_id}`。
- 在 `app/routes.tsx` 注册 tenancy 路由 + 导航(net-new,不涉及 legacyLinks)。

## Capabilities

### New Capabilities
- `tenancy-admin-ui`: Tenancy 域在 React SPA 中原生管理——租户/团队列表与创建、用户到租户的分配、审批人设置。

### Modified Capabilities
（无）

## Impact

- **新增**:`frontend/src/features/tenancy/`(api/page/test)。
- **改动**:`frontend/src/app/routes.tsx`(注册 tenancy + 导航)——共享缝,机械可解。
- **后端**:不改(tenancy admin API 已完整)。
- **边界**:纯 `frontend/`;不碰 server.py / agent / schema。net-new(无 legacy parity,按后端 API 能力建)。建在 C1 壳上。**合并由主会话串行做。**
