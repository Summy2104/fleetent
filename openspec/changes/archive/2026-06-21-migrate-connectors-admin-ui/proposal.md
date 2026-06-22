## Why

Connectors 域(legacy 的 #oauth tab,含 OAuth 外部服务 + MCP servers)目前只在新 SPA 里深链回 legacy,且 legacy 是 **create-only**——OAuth 连接器和 MCP server 都能建不能改/删/测,配错锁死。本切片把 Connectors 迁成新 SPA 原生域,补齐 edit/delete/test(pillar-2 缺口)。

## What Changes

- 新增 `features/connectors/`(`api.ts` + `page.tsx` + `page.test.tsx`),照 C1 agents 范式(TanStack Query + MSW + TDD)。
- **OAuth 外部服务**(`/admin/connectors`):列表 `GET ""`、建 `POST ""`、**改 `PUT /{id}`**、**删 `DELETE /{id}`**、**测试 `POST /{id}/test``**、生命周期 `GET /{id}/lifecycle`、agent 绑定 `GET /{id}/bindings/agents`、授权矩阵(grants `GET /connectors/grants`、撤销 `POST /grants/{user}/{conn}/revoke`、offboarding `GET /offboarding/{user}`)、写凭证 `POST /{service_id}/credentials`、授权/回调流(`GET /connectors/authorize/{service}`、`/callback/{service}`)。
- **MCP servers**(`/admin/mcp/servers`):列表 `GET`、建 `POST`、**改 `PUT /{id}`**、**删 `DELETE /{id}`**、**测试 `POST /{id}/test`**、重连 `POST /{id}/reconnect`、工具列表 `GET /{id}/tools`、doctor `GET /mcp/doctor`。
- 在 `app/routes.tsx` 注册 connectors 路由 + 导航(#oauth),并从 `legacyLinks` 移除 Connectors。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `oauth-connector-admin`: 新增"OAuth 外部服务在 React SPA 中原生完整管理(建/改/删/测试 + 授权矩阵/撤销/offboarding + 写凭证)"——闭合 create-only。
- `mcp-server-admin`: 新增"MCP server 在 React SPA 中原生完整管理(建/改/删/测试/重连/工具/doctor)"——闭合 create-only。

## Impact

- **新增**:`frontend/src/features/connectors/`(api/page/test)。
- **改动**:`frontend/src/app/routes.tsx`(注册 connectors + 从 legacyLinks 移除 Connectors)——**与同批其它域 change 的唯一共享文件,机械可解**。
- **后端**:不改(OAuth + MCP admin API 已完整)。
- **边界**:纯 `frontend/`;不碰 agent 运行时、server.py、schema。建在 C1 壳之上。与 ④ gateway(后端)零重叠。OAuth 授权/回调是浏览器跳转流,沿用既有后端端点,不在前端持密钥。
