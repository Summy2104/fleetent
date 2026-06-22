## Why

KB 域目前只在新 SPA 里深链回 legacy,且 KB 的**内容生命周期(建库、灌文档、sync、连接器)运维只能走 API/CLId**——pillar-2 的大缺口。本切片把 KB 迁成新 SPA 原生域,补齐内容管理。

## What Changes

- 新增 `features/kb/`(`api.ts` + `page.tsx` + `page.test.tsx`),照 C1 agents 范式(TanStack Query + MSW + TDD)。
- 覆盖既有 admin API(`/admin/kb`):库 列表 `GET ""`、建 `POST ""`、改 `PATCH /{id}`、删 `DELETE /{id}`;文档 灌入 `POST /{id}/documents`、列表 `GET /{id}/documents`、删 `DELETE /{id}/documents/{doc}`、同步 `POST /{id}/sync`;KB 连接器 列表/建/改/删 + 检查 `POST /connectors/{id}/check`、状态 `GET /connectors/{id}/status`、同步 `POST /connectors/{id}/sync`;agent 绑定查看 `GET /{id}/agents`。
- 在 `app/routes.tsx` 注册 kb 路由 + 导航,并从 `legacyLinks` 移除 Knowledge Base。
- 检索 playground(`POST /search`)/ extract-entities / observation 为可选增强,优先保内容生命周期 parity。

## Capabilities

### New Capabilities
- `kb-admin-ui`: KB 域在 React SPA 中原生管理——库 CRUD、文档灌入/列表/删除/同步、KB 连接器注册/检查/同步、agent 绑定查看。

### Modified Capabilities
（无）

## Impact

- **新增**:`frontend/src/features/kb/`(api/page/test)。
- **改动**:`frontend/src/app/routes.tsx`(注册 kb + 从 legacyLinks 移除 Knowledge Base)——**与同批其它域 change 的唯一共享文件,机械可解**。
- **后端**:不改(KB admin API 已完整)。
- **边界**:纯 `frontend/`;不碰 agent 运行时、server.py、schema。建在 C1 壳之上。与正在跑的 ④ gateway(后端)零重叠。
