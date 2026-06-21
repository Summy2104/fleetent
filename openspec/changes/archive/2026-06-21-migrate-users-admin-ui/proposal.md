## Why

C1 只迁了 agents 域;users 仍走 legacy。而 legacy 的 users 缺一个真实运维能力:**API key 只能建、不能在 UI 吊销/轮换**(`DELETE /admin/keys/{id}`、`POST /users/{id}/rotate-key` 后端有、UI 无)。本切片把 users 域迁成新 SPA 原生页,并补齐 key 吊销/轮换(pillar-2 缺口)。

## What Changes

- 新增 `features/users/`(`api.ts` + `page.tsx` + `page.test.tsx`),照 C1 agents 范式(TanStack Query + MSW + TDD)。
- 覆盖既有 admin API:用户列表 `GET /admin/users`、建用户 `POST /admin/users`、改 `PATCH /admin/users/{id}`、角色 `PATCH /admin/users/{id}/role`、封/解封 `POST .../block`·`/unblock`、重置密码 `POST .../password`、删 `DELETE /admin/users/{id}`;API key 列表 `GET /admin/users/{id}/keys`、建 `POST .../keys`、**轮换 `POST .../rotate-key`**、**吊销 `DELETE /admin/keys/{key_id}`**;IM 身份 `GET /admin/im-users` 及 bind/block/restore(与 legacy users 标签 parity)。
- 在 `app/routes.tsx` 注册 users 路由 + 导航。

## Capabilities

### New Capabilities
(无)

### Modified Capabilities
- `web-user-management`: 新增"users 域在 React SPA 中原生管理(建/改/角色/封禁/删 + IM 身份)"的要求。
- `api-key-management`: 新增"在 SPA 中吊销/轮换某个 API key"的要求——闭合 legacy 只能建不能撤的缺口。

## Impact

- **新增**:`frontend/src/features/users/`(api/page/test)。
- **改动**:`frontend/src/app/routes.tsx`(注册 users + 导航)——**与其它域 change 的唯一共享文件,3 行登记,机械可解**。
- **后端**:不改(user/key admin API 已完整,含 revoke/rotate)。
- **边界**:纯 `frontend/`;不碰 agent 运行时、不碰 server.py、无 schema。建在 C1 壳之上。
