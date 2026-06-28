# oauth-mcp-admin-ui Specification

## Purpose
记录 admin SPA 中 OAuth connectors 面的退役结果，以及 MCP 面仍保留的边界。

## REMOVED Requirements

### Requirement: OAuth connectors tab
**Reason**: OAuth connectors 的 platform 控制面已退役。
**Migration**: 删 `/connectors` 路由、导航和 i18n；相关后端端点同步移除。

### Requirement: Connector CRUD and grant revoke
**Reason**: 旧管理面不再存在。
**Migration**: 删除前端 connector 增删改与 grant 吊销控件。

## Requirements

### Requirement: MCP servers view
The console SHALL show MCP server states with a doctor summary and let an admin reconnect a server and view its tools.

#### Scenario: Reconnect an MCP server
- **WHEN** an admin clicks reconnect on a listed MCP server
- **THEN** the console calls `POST /admin/mcp/servers/{server_id}/reconnect`
