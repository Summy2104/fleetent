## Why

C1 把管理前端换成 React SPA,但只迁了 agents 域;providers 仍只在新 SPA 里**深链回 legacy**。而 legacy 的 providers 是 **create-only**——能建不能改/删/测,配错的 provider 在 UI 里锁死、只能走 CLI 修。本切片把 providers 迁成新 SPA 的原生域,并顺带补齐 edit/delete/连通测试(pillar-2 缺口)。

## What Changes

- 在新 SPA 新增 `features/providers/`(`api.ts` + `page.tsx` + `page.test.tsx`),照 C1 agents 范式(TanStack Query + MSW 测 + TDD)。
- 覆盖完整 CRUD + 运维动作,均调既有 admin API:列表 `GET /admin/providers`、建 `POST /admin/providers`、**改 `PUT /admin/providers/{id}`**、**删 `DELETE /admin/providers/{id}`**、**连通测试 `POST /admin/providers/{id}/connectivity-test`**、定价 `PUT /admin/providers/{id}/pricing`。
- 在 `app/routes.tsx` 注册 providers 路由 + 导航,并从 `legacyLinks` 移除 providers。
- api_key 在任何视图/响应中保持遮蔽(沿用后端既有遮蔽,不在前端反显)。

## Capabilities

### New Capabilities
(无)

### Modified Capabilities
- `provider-admin-ui`: 新增"providers 域在 React SPA 中原生渲染且支持完整 CRUD(建/改/删/连通测试/定价)"的要求——闭合 legacy 的 create-only 缺口。

## Impact

- **新增**:`frontend/src/features/providers/`(api/page/test)。
- **改动**:`frontend/src/app/routes.tsx`(注册 providers + 从 legacyLinks 移除)——**与其它域 change 的唯一共享文件,3 行登记,merge 时机械可解**。
- **后端**:不改(provider admin API 已完整)。
- **边界**:纯 `frontend/`;不碰 agent 运行时、不碰 server.py、无 schema。建在 C1 壳(已在 main)之上。
