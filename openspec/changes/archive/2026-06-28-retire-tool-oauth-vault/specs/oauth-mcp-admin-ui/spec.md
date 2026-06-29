## REMOVED Requirements

### Requirement: OAuth connectors tab
**Reason**: 退役工具 OAuth Vault 的前端面——OAuth Connectors tab 列外部服务注册表与 per-user grants 矩阵，二者随 Vault 退役。
**Migration**: 删控制台 OAuth Connectors tab 及 `/connectors` 导航/i18n；后端 `GET /admin/connectors`、`GET /admin/connectors/grants` 同步移除（见 `oauth-connector-admin` delta）。MCP servers view 不受影响、保留。

### Requirement: Connector CRUD and grant revoke
**Reason**: 随 OAuth Connectors tab 与 grants 管理端点退役。
**Migration**: 删前端 connector 增删改与 grant 吊销控件。

> 注：本 spec 的 `### Requirement: MCP servers view` **不在本 change 范围**、保留不动；MCP 管理 UI 的后续调整属 change ② `slim-mcp-to-agent-auth`。
