> 前端 TDD 硬门禁:先写测试见红 → 实现见绿。最窄 `yarn --cwd frontend vitest run <file>`。测试先于实现。照 C1 `features/agents/` 范式。

## 1. 数据层(api.ts,TDD)

- [x] 1.1 写测试(Vitest+MSW):skills hooks(list/content/enable/disable/delete/restore/force-publish/reload/agent 绑定/versions/diff)+ 提案只读 hooks(proposals 列表、proposal diff);mutation 后失效列表。先见红。
- [x] 1.2 实现 `features/skills/api.ts`(照 agents/api.ts,经 `useAdminApi`)。跑 1.1 见绿。

## 2. 页面(page.tsx,TDD)

- [x] 2.1 写测试(`page.test.tsx`,MSW):列表/内容查看/启停/删恢复/强发/重扫/agent 绑定/版本 diff;提案区只读(列表 + diff,**断言无 approve/reject 控件**)。先见红。
- [x] 2.2 实现 `features/skills/page.tsx`,与 legacy #skills tab parity。跑 2.1 见绿。

## 3. 路由注册(共享缝)

- [x] 3.1 在 `app/routes.tsx` 注册 skills(import + nav NavLink + Route),并从 `legacyLinks` 移除 Skills;补 `routes.test.tsx` 断言(用 `within(nav)` scope)。

## 4. Change 收尾验证

- [x] 4.1 `make test-frontend` 全绿(vitest + 覆盖率阈值 + tsc --noEmit + lint)。
- [x] 4.2 `make test-pr` 全绿(对照 main 基线无新增失败)。
- [x] 4.3 手动核对:`/admin/ui` 内 skills 原生页可列表/启停/看内容/看提案 diff;无 approve/reject;导航不再深链 legacy Skills。
