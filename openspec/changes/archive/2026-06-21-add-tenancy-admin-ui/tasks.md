> 前端 TDD 硬门禁:先写测试见红 → 实现见绿。最窄 `yarn --cwd frontend vitest run <file>`。测试先于实现。照 C1 `features/agents/` 范式。net-new 域,按 `/admin/tenancy` 实际 API 能力建。合并由主会话串行做。

## 1. 数据层(api.ts,TDD)

- [x] 1.1 写测试(Vitest+MSW):tenants/teams 的 query + create hooks、`useAssignUserTenant`、`useSetApprover`;mutation 后失效相关列表。先见红。
- [x] 1.2 实现 `features/tenancy/api.ts`(照 agents/api.ts,经 `useAdminApi`)。跑 1.1 见绿。

## 2. 页面(page.tsx,TDD)

- [x] 2.1 写测试(`page.test.tsx`,MSW):租户列表/建、团队列表/建、用户分配租户、设审批人;viewer 只读。先见红。
- [x] 2.2 实现 `features/tenancy/page.tsx`。跑 2.1 见绿。

## 3. 路由注册(共享缝)

- [x] 3.1 在 `app/routes.tsx` 注册 tenancy(import + nav NavLink + Route);补 `routes.test.tsx` 断言(`within(nav)` scope)。

## 4. Change 收尾验证

- [x] 4.1 `make test-frontend` 全绿(vitest + 覆盖率阈值 + tsc --noEmit + lint)。
- [x] 4.2 `make test-pr` 全绿(对照 main 基线无新增失败)。
- [ ] 4.3 手动核对:`/admin/ui` 内 Tenancy 原生页可建/列租户与团队、分配用户、设审批人。
