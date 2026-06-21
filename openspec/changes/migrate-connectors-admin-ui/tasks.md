> 前端 TDD 硬门禁:先写测试见红 → 实现见绿。最窄 `yarn --cwd frontend vitest run <file>`。测试先于实现。照 C1 `features/agents/` 范式。

## 1. 数据层(api.ts,TDD)

- [ ] 1.1 写测试(Vitest+MSW):OAuth hooks(list/create/update/delete/test/lifecycle/bindings/grants/revoke/offboarding/credentials)与 MCP hooks(list/create/update/delete/test/reconnect/tools/doctor);mutation 后失效列表。先见红。
- [ ] 1.2 实现 `features/connectors/api.ts`(照 agents/api.ts,经 `useAdminApi`)。跑 1.1 见绿。

## 2. 页面(page.tsx,TDD)

- [ ] 2.1 写测试(`page.test.tsx`,MSW):OAuth 子区(列表/建/改/删/测/授权矩阵/撤销;断言不反显凭证)+ MCP 子区(列表/建/改/删/测/重连/工具/doctor)。先见红。
- [ ] 2.2 实现 `features/connectors/page.tsx`(两子区),与 legacy #oauth tab 两块逐条 parity + 补 edit/delete/test。跑 2.1 见绿。

## 3. 路由注册(共享缝)

- [ ] 3.1 在 `app/routes.tsx` 注册 connectors(import + nav NavLink + Route),并从 `legacyLinks` 移除 Connectors;补 `routes.test.tsx` 断言(用 `within(nav)` scope)。

## 4. Change 收尾验证

- [ ] 4.1 `make test-frontend` 全绿(vitest + 覆盖率阈值 + tsc --noEmit + lint)。
- [ ] 4.2 `make test-pr` 全绿(对照 main 基线无新增失败)。
- [ ] 4.3 手动核对:`/admin/ui` 内 Connectors 原生页 OAuth + MCP 都可建/改/删/测;导航不再深链 legacy Connectors。
