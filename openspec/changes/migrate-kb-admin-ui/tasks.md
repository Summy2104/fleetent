> 前端 TDD 硬门禁:先写测试见红 → 实现见绿。最窄 `yarn --cwd frontend vitest run <file>`。测试先于实现。照 C1 `features/agents/` 范式。

## 1. 数据层(api.ts,TDD)

- [ ] 1.1 写测试(Vitest+MSW):库 hooks(list/create/update/delete)、文档 hooks(ingest/list/delete/sync)、KB 连接器 hooks(list/create/update/delete/check/status/sync);mutation 后失效相关列表。先见红。
- [ ] 1.2 实现 `features/kb/api.ts`(照 agents/api.ts,经 `useAdminApi`)。跑 1.1 见绿。

## 2. 页面(page.tsx,TDD)

- [ ] 2.1 写测试(`page.test.tsx`,MSW):库列表/建/改/删;详情的文档面板(灌入/列表/删除/同步)与连接器面板(注册/检查/状态/同步);长操作的进行中/结果反馈。先见红。
- [ ] 2.2 实现 `features/kb/page.tsx`,与 legacy #kb tab 逐块 parity。跑 2.1 见绿。

## 3. 路由注册(共享缝)

- [ ] 3.1 在 `app/routes.tsx` 注册 kb(import + nav NavLink + Route),并从 `legacyLinks` 移除 Knowledge Base;补 `routes.test.tsx` 断言 kb 为原生路由、不在 legacy 链(用 `within(nav)` scope,避免与其它同名链二义)。

## 4. Change 收尾验证

- [ ] 4.1 `make test-frontend` 全绿(vitest + 覆盖率阈值 + tsc --noEmit + lint)。
- [ ] 4.2 `make test-pr` 全绿(对照 main 基线无新增失败)。
- [ ] 4.3 手动核对:`/admin/ui` 内 KB 原生页可建库/灌文档/删/同步、管连接器;导航不再深链 legacy KB。
