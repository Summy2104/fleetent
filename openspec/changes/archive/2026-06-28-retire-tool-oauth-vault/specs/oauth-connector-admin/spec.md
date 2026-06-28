## REMOVED Requirements

> **共同 Reason**：`/admin/connectors*` 服务目录与 grants 管理 API 是工具 OAuth Vault 的管理面，随 Vault 退役（零生产工具消费、前端 OAuth tab 从未渲染）。
> **共同 Migration**：删 `connector_admin_api.py` 的 connector 目录/grants/consent/吊销端点；前端 OAuth 面随 `oauth-mcp-admin-ui` 同步移除。工具凭证管理改由 agent 侧承载。

### Requirement: Connector directory and configuration
**Reason**: 退役工具 OAuth Vault 管理面。
**Migration**: 删 `/admin/connectors` 目录端点（list/add/edit/delete）。

### Requirement: Per-user authorization matrix
**Reason**: 随 `external_credentials` 退役，无授权矩阵可呈现。
**Migration**: 删 `/admin/connectors/grants`。

### Requirement: Admin cannot complete first-time consent on behalf of a user
**Reason**: 随 OAuth consent 流退役。
**Migration**: 该护栏随 consent 端点删除。

### Requirement: Admin revoke on behalf of a user
**Reason**: 随凭证吊销退役。
**Migration**: 删管理员代吊销路径。

### Requirement: Offboarding linkage visibility
**Reason**: 随 `external_credentials` 退役，无 per-principal 凭证可关联离场。
**Migration**: 删离场关联视图。

### Requirement: Credential lifecycle observability
**Reason**: 随 `external_credentials` 状态退役。
**Migration**: 删凭证生命周期可观测端点。

### Requirement: Sensitive value masking across all views
**Reason**: 随 connector 目录/grants 视图退役，无敏感字段视图需脱敏。
**Migration**: 脱敏要求随相关端点删除。

### Requirement: OAuth connectors managed natively in the React SPA
**Reason**: 退役前端 OAuth 管理面。
**Migration**: 删 SPA 内 OAuth connectors 管理（见 `oauth-mcp-admin-ui` delta）。
