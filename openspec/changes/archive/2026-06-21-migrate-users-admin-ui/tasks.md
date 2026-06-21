> 前端 TDD 硬门禁:先写测试见红 → 实现见绿。最窄命令 `yarn --cwd frontend vitest run <file>`。测试先于实现。照 C1 `features/agents/` 范式。

## 1. 数据层(api.ts,TDD)

- [x] 1.1 写测试(Vitest+MSW):用户 hooks(list/create/update/role/block/unblock/password/delete)+ key hooks(list/create/**rotate**/**revoke**)+ IM 身份 hooks;mutation 成功后失效相关列表。先见红。
- [x] 1.2 实现 `features/users/api.ts`(照 agents/api.ts,经 `useAdminApi`)。跑 1.1 见绿。

## 2. 页面(page.tsx,TDD)

- [x] 2.1 写测试(`page.test.tsx`,MSW):用户列表/建/改/角色/封禁/删;每用户的 key 面板(列表掩码、建/轮换一次性展示明文、吊销确认);IM 身份 bind/block/restore。断言明文 key 不回显/不重复拉取。先见红。
- [x] 2.2 实现 `features/users/page.tsx`,与 legacy users 标签逐条 parity + 补 key 吊销/轮换。跑 2.1 见绿。

## 3. 路由注册(共享缝)

- [x] 3.1 在 `app/routes.tsx` 注册 users(import + nav NavLink + Route);补 `routes.test.tsx` 断言 users 为原生路由。

## 4. Change 收尾验证

- [x] 4.1 `make test-frontend` 全绿(vitest + 覆盖率阈值 + tsc --noEmit + lint)。
- [x] 4.2 `make test-pr` 全绿(对照 main 基线无新增失败)。
- [x] 4.3 手动核对:`/admin/ui` 内 users 原生页可建/改/角色/封禁/删;key 能建/轮换/吊销且明文只显示一次。
