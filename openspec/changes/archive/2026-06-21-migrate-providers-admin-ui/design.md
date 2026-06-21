## Context

C1(`admin-frontend-react-foundation`,已在 main)立了 React+TS+Vite 的 SPA 壳:`features/agents/`(`api.ts` typed query/mutation hooks via `useAdminApi` + TanStack Query;`page.tsx`;`page.test.tsx` MSW)是已坐实的"港一个域"范式;域在 `app/routes.tsx` 三处登记(import + nav NavLink + Route),未迁域走 `legacyLinks` 深链。本切片照此范式港 providers。

## Goals / Non-Goals

**Goals:** providers 域原生进 SPA,完整 CRUD + 连通测试 + 定价,与 legacy parity 并补齐 edit/delete/test;TDD + MSW 覆盖。
**Non-Goals:** 不改 provider 后端 API(已完整);不动其它域;不引入新组件库依赖(用 C1 既有 shadcn/ui + TanStack Query)。

## Decisions

**D1 · 照 agents 范式 1:1 复制结构。** `features/providers/api.ts` 暴露 `useProvidersQuery` / `useCreateProvider` / `useUpdateProvider` / `useDeleteProvider` / `useConnectivityTest` / `useUpdatePricing`,mutation 成功后 `invalidateQueries(['providers'])` 刷新列表。`page.tsx` 列表 + 建/改弹窗(双模)+ 删除确认 + 测试连通按钮。

**D2 · 闭合 create-only。** legacy 只有"建";本域必须含 edit(`PUT`)、delete(`DELETE`,带确认)、connectivity-test(`POST`),让配错的 provider 能在 UI 改/删/验。

**D3 · routes.tsx 是唯一共享缝。** 登记 providers(import + NavLink + Route)并从 `legacyLinks` 删 providers。与并行的 users/sessions change 只在此文件相撞,3 行相邻、机械可解。

## Risks / Trade-offs

- **[与并行域 change 撞 routes.tsx]** → 仅 3 行登记,merge 时保留各域条目即可;无逻辑冲突。
- **[api_key 反显泄露]** → 前端只渲染后端返回的(已遮蔽)字段,建/改表单的 key 输入只写不回显;测试断言响应/渲染不含明文 key。
- **[parity 漏项]** → 以 legacy providers 区块能力为基准逐条对照(列表字段、建、改、删、测试、定价)。
