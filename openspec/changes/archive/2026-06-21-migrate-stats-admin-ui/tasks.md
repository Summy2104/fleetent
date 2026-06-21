> 前端 TDD 硬门禁:先写测试见红 → 实现见绿。最窄 `yarn --cwd frontend vitest run <file>`。测试先于实现。照 C1 `features/agents/` 范式。合并由主会话串行做(窗口只实现 + push)。

## 1. 数据层(api.ts,TDD)

- [x] 1.1 写测试(Vitest+MSW):只读查询 hooks(overview/compare/tools/per-user/user-requests/request-detail/session-trace)+ 导出(`POST /export`)。先见红。
- [x] 1.2 实现 `features/stats/api.ts`(TanStack Query;导出走 fetch+blob)。跑 1.1 见绿。

## 2. 页面(page.tsx,TDD)

- [x] 2.1 写测试(`page.test.tsx`,MSW):per-user 列表 / agent overview / compare / 请求·会话 trell 渲染;导出触发。先见红。
- [x] 2.2 实现 `features/stats/page.tsx`,与 legacy #stats tab parity。跑 2.1 见绿。

## 3. 路由注册(共享缝)

- [x] 3.1 在 `app/routes.tsx` 注册 stats(import + nav NavLink + Route),并从 `legacyLinks` 移除 Statistics;补 `routes.test.tsx` 断言(`within(nav)` scope)。

## 4. Change 收尾验证

- [x] 4.1 `make test-frontend` 全绿(vitest + 覆盖率阈值 + tsc --noEmit + lint)。
- [x] 4.2 `make test-pr` 全绿(对照 main 基线无新增失败)。
- [ ] 4.3 手动核对:`/admin/ui` 内 Statistics 原生页可看 per-user/overview/compare/trace、导出;导航不再深链 legacy。
