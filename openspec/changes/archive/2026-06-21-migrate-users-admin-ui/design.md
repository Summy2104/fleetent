## Context

C1(已在 main)的 `features/agents/` 是已坐实的"港一个域"范式(`api.ts` TanStack Query hooks via `useAdminApi`;`page.tsx`;MSW 测);域在 `app/routes.tsx` 三处登记,未迁域走 `legacyLinks`。本切片照此港 users。

## Goals / Non-Goals

**Goals:** users 域原生进 SPA,与 legacy users 标签 parity(用户 CRUD/角色/封禁/密码、API key、IM 身份),并补齐 **key 吊销/轮换**;TDD + MSW 覆盖。
**Non-Goals:** 不改后端 user/key API(已完整);不动其它域;不引入新依赖。

## Decisions

**D1 · 照 agents 范式。** `features/users/api.ts` 暴露用户与 key 的 query/mutation hooks(`useUsersQuery`、`useCreateUser`、`useUpdateUser`、`useSetRole`、`useBlockUser`/`useUnblockUser`、`useResetPassword`、`useDeleteUser`;`useUserKeysQuery`、`useCreateKey`、`useRotateKey`、`useRevokeKey`;IM 身份 hooks),mutation 后失效相关列表。

**D2 · 闭合 key 不能撤的缺口。** 必须含 `useRevokeKey`(`DELETE /admin/keys/{key_id}`,带确认)与 `useRotateKey`(`POST /admin/users/{id}/rotate-key`,新 key 一次性展示)。

**D3 · 新 key/明文凭证一次性展示、不回显。** 建/轮换返回的明文 key 仅展示一次并提示复制;列表只显示 prefix/掩码;测试断言明文 key 不被持久渲染或再次拉取。

**D4 · routes.tsx 唯一共享缝。** 登记 users(import + NavLink + Route)。与并行的 providers/sessions change 仅此文件相撞,机械可解。

## Risks / Trade-offs

- **[与并行域撞 routes.tsx]** → 3 行登记,merge 保留各域条目即可。
- **[明文 key 泄露]** → 一次性展示 + 不回显 + 不重复 GET;测试守这条。
- **[parity 漏项]** → 以 legacy users 标签能力清单逐条对照(用户列表/建/改/角色/封禁/删、key 列表/建/轮换/吊销、IM 身份 bind/block/restore)。
