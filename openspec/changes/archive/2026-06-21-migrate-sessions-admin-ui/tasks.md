> 前端 TDD 硬门禁:先写测试见红 → 实现见绿。最窄命令 `yarn --cwd frontend vitest run <file>`。测试先于实现。照 C1 `features/agents/` 范式。

## 1. 数据层(api.ts,TDD)

- [x] 1.1 写测试(Vitest+MSW):`useSessionsQuery` 列表、`useSessionDetail`;治理 mutation(takeover/release/inject/force-end/clear/reset/bulk)调对应端点,成功后失效列表/详情。先见红。
- [x] 1.2 实现 `features/sessions/api.ts`(照 agents/api.ts,经 `useAdminApi`)。跑 1.1 见绿。

## 2. 页面(page.tsx,TDD)

- [x] 2.1 写测试(`page.test.tsx`,MSW):会话列表/筛选、详情;治理动作;高危动作(force-end/clear/reset/批量)二次确认;viewer 只读(写控件隐藏/拒绝)。先见红。
- [x] 2.2 实现 `features/sessions/page.tsx`,与 legacy sessions 区块逐条 parity(不含 playground)。跑 2.1 见绿。

## 3. 路由注册(共享缝)

- [x] 3.1 在 `app/routes.tsx` 注册 sessions(import + nav NavLink + Route);补 `routes.test.tsx` 断言 sessions 为原生路由。

## 4. Change 收尾验证

- [ ] 4.1 `make test-frontend` 全绿(vitest + 覆盖率阈值 + tsc --noEmit + lint)。
- [ ] 4.2 `make test-pr` 全绿(对照 main 基线无新增失败)。
- [ ] 4.3 手动核对:`/admin/ui` 内 sessions 原生页可列表/详情/治理;高危动作有二次确认;viewer 只读。
