> 前端 TDD 硬门禁:每个功能先写测试见红 → 实现见绿。最窄命令 `yarn --cwd frontend vitest run <file>`。测试任务先于实现。照 C1 `features/agents/` 范式。

## 1. 数据层(api.ts,TDD)

- [ ] 1.1 写测试(Vitest+MSW):`useProvidersQuery` 列表加载;`useCreateProvider`/`useUpdateProvider`/`useDeleteProvider`/`useConnectivityTest`/`useUpdatePricing` 调对应端点,mutation 成功后 `['providers']` 失效刷新。先见红。
- [ ] 1.2 实现 `features/providers/api.ts`(照 agents/api.ts 模式,经 `useAdminApi`)。跑 1.1 见绿。

## 2. 页面(page.tsx,TDD)

- [ ] 2.1 写测试(`page.test.tsx`,MSW):列表渲染(api_key 遮蔽)、建/改双模弹窗、删除确认、连通测试按钮显示结果。先见红。
- [ ] 2.2 实现 `features/providers/page.tsx`(列表 + 建/改 + 删 + 测试 + 定价),与 legacy providers 区块逐条 parity。跑 2.1 见绿。

## 3. 路由注册(共享缝)

- [ ] 3.1 在 `app/routes.tsx` 注册 providers(import + nav NavLink + Route),并从 `legacyLinks` 移除 providers。更新/补 `routes.test.tsx` 断言 providers 为原生路由、不在 legacy 链。

## 4. Change 收尾验证

- [ ] 4.1 `make test-frontend` 全绿(vitest + 覆盖率阈值 + tsc --noEmit + lint)。
- [ ] 4.2 `make test-pr` 全绿(对照 main 基线无新增失败)。
- [ ] 4.3 手动核对:`/admin/ui` 内 providers 原生页可列表/建/改/删/测;导航不再深链 legacy providers。
