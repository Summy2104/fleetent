## Why

Skills 域目前只在新 SPA 里深链回 legacy。本切片把 skills 迁成新 SPA 原生域,与 legacy parity。

## What Changes

- 新增 `features/skills/`(`api.ts` + `page.tsx` + `page.test.tsx`),照 C1 agents 范式(TanStack Query + MSW + TDD)。
- 覆盖既有 admin API(`/admin/skills`):列表 `GET ""`、内容查看 `GET /{name}/content`、启用/禁用 `POST /{name}/enable`·`/disable`、删/恢复 `DELETE /{name}`·`POST /{name}/restore`、强制发布 `POST /{name}/force-publish`、重扫 `POST /reload`、agent 绑定 `GET /{name}/agents`·`PUT /{name}/agents/{agent_id}`、版本/diff `GET /{name}/versions`·`/versions/{ref}/diff`;提案**查看**(列表 `GET /proposals`、diff `GET /proposals/{id}/diff`)。
- 提案的 approve/reject **不做**——它们是 agent-owned、经 DM(prune 已删平台审批桩);SPA 只读列表 + diff。
- 在 `app/routes.tsx` 注册 skills 路由 + 导航,并从 `legacyLinks` 移除 Skills。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `skill-admin-ui`: 新增"skills 域在 React SPA 中原生管理(列表/内容/启停/删恢复/强发/重扫/agent 绑定/版本 diff)+ 提案只读查看(列表+diff,无 approve/reject)"的要求。

## Impact

- **新增**:`frontend/src/features/skills/`(api/page/test)。
- **改动**:`frontend/src/app/routes.tsx`(注册 skills + 从 legacyLinks 移除 Skills)——**与同批其它域 change 的唯一共享文件,机械可解**。
- **后端**:不改(skill admin API 已完整;approve/reject 桩已于 prune 删除)。
- **边界**:纯 `frontend/`;不碰 agent 运行时、server.py、schema。建在 C1 壳之上。与 ④ gateway(后端)零重叠。
