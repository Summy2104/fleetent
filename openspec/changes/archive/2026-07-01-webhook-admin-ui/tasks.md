> 前端 TDD 硬门禁：先写测试见红 → 实现见绿。最窄命令 `yarn --cwd frontend vitest run <file>`。测试先于实现。照 `features/mcp/` 范式。

## 1. 数据层（api.ts，TDD）

- [x] 1.1 写测试（Vitest + MSW）：webhook hooks（list/create/delete），mutation 后失效列表查询。先见红。
- [x] 1.2 实现 `features/webhooks/api.ts`（类型定义 + hooks，照 `features/connectors/api.ts` 风格）。跑 1.1 见绿。

## 2. 页面（page.tsx，TDD）

- [x] 2.1 写测试（`page.test.tsx`，MSW）：列表渲染、新建弹窗（agent/user 下拉必填校验、secret 随机生成按钮）、删除确认、创建成功后展示可复制的 webhook URL。先见红。
- [x] 2.2 实现 `features/webhooks/page.tsx`。跑 2.1 见绿。

## 3. 路由 / 导航 / i18n 接入

- [x] 3.1 `app/routes.tsx` 注册 `/webhooks` 路由；`app/nav.ts` 的 `nav.group.integrations` 分组加导航项；`i18n/messages.ts` 补 `webhooks.*` + `nav.webhooks` 的 en + zh 词条（en 权威源，zh 类型强制对齐，两边都要写）。现有 `routes.test.tsx` 断言均按具体命名 link 校验，未依赖导航总数，新增项不影响既有断言，未额外补充。

## 4. Change 收尾验证

- [x] 4.1 `make test-frontend` 全绿（vitest + 覆盖率阈值 + tsc --noEmit + lint）。
- [x] 4.2 手动核对：`/admin/ui` 内可新建/列出/删除 webhook source，创建后能复制出可用 URL（本地起 platform + vite dev server，用 Playwright 实际登录走完新建/展示 URL/删除全流程，均符合预期）。
