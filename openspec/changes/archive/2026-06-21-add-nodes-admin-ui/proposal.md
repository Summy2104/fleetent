## Why

多节点编排(nodes / agent placement)后端齐全(`node_admin_api`),但**全程无 UI**——运维只能 CLI/API 管节点与 agent 放置(标准 2 的 MISSING 项)。本切片在新 SPA 加一个原生 Nodes 域(net-new,无 legacy tab 可参照),让运维在页面上看节点、注册/删除、把 agent pin/unpin 到节点。

## What Changes

- 新增 `features/nodes/`(`api.ts` + `page.tsx` + `page.test.tsx`),照 C1 agents 范式(TanStack Query + MSW + TDD)。
- 覆盖既有 admin API(`/admin/nodes`):列表 `GET ""`(id/name/labels/last_seen/注册时间)、注册 `POST ""`、删除 `DELETE /{id}`(带确认)、把 agent pin 到节点 `POST /{id}/pin`、unpin `DELETE /{id}/pin`。
- 在 `app/routes.tsx` 注册 nodes 路由 + 导航(net-new,不涉及 legacyLinks)。

## Capabilities

### New Capabilities
- `node-admin-ui`: Nodes 域在 React SPA 中原生管理——节点列表/注册/删除 + agent 到节点的 pin/unpin 放置。

### Modified Capabilities
（无）

## Impact

- **新增**:`frontend/src/features/nodes/`(api/page/test)。
- **改动**:`frontend/src/app/routes.tsx`(注册 nodes + 导航)——共享缝,机械可解。
- **后端**:不改(node admin API 已完整)。
- **边界**:纯 `frontend/`;不碰 server.py / agent / schema。net-new(无 legacy parity 基线,按后端 API 能力建)。建在 C1 壳上。**合并由主会话串行做。**
- **说明**:节点删除是高危(影响其上 agent 放置),UI 需二次确认。
