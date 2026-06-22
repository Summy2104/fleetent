## Why

C1 只迁了 agents 域;sessions 仍走 legacy。sessions 治理(列出会话、接管/注入/强制结束/清空/重置)是运维刚需,后端 API 已完整。本切片把 sessions 域迁成新 SPA 原生页(prune 已移除的 chat playground 不重建——只做会话列表 + 治理)。

## What Changes

- 新增 `features/sessions/`(`api.ts` + `page.tsx` + `page.test.tsx`),照 C1 agents 范式(TanStack Query + MSW + TDD)。
- 覆盖既有 admin API:列表 `GET /admin/sessions`、详情 `GET /admin/sessions/{id}`、接管 `POST .../takeover`、释放 `.../release`、注入 `.../inject`、强制结束 `.../force-end`、清空 `.../clear`、重置 `.../reset`、批量 `POST /admin/sessions/bulk`。
- 高危动作(force-end/clear/reset/批量)需二次确认;写操作 admin-only,viewer 只读。
- 在 `app/routes.tsx` 注册 sessions 路由 + 导航。

## Capabilities

### New Capabilities
(无)

### Modified Capabilities
- `session-admin-ui`: 新增"sessions 域在 React SPA 中原生渲染:会话列表 + 治理动作(接管/释放/注入/强制结束/清空/重置/批量),高危二次确认、viewer 只读"的要求。不含 chat playground(已于 prune 移除)。

## Impact

- **新增**:`frontend/src/features/sessions/`(api/page/test)。
- **改动**:`frontend/src/app/routes.tsx`(注册 sessions + 导航)——**与其它域 change 的唯一共享文件,3 行登记,机械可解**。
- **后端**:不改(session 治理 API 已完整)。
- **边界**:纯 `frontend/`;不碰 agent 运行时、不碰 server.py、无 schema。建在 C1 壳之上。
