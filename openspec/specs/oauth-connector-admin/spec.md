# oauth-connector-admin Specification

## Purpose
该管理面已从 platform 移除；本 spec 记录其退役状态，防止旧路由和旧 UI 重新挂回控制面。

## REMOVED Requirements

### Requirement: Connector directory and configuration
**Reason**: platform 不再维护工具凭证服务目录。
**Migration**: 删 `/admin/connectors` 的 list / create / update / delete。

### Requirement: Per-user authorization matrix
**Reason**: platform 不再持有 per-principal 工具凭证状态。
**Migration**: 删 `/admin/connectors/grants` 及其聚合视图。

### Requirement: Admin cannot complete first-time consent on behalf of a user
**Reason**: 整个 consent 管理面已退役。
**Migration**: 删除相关端点后，该约束自然失效，不再由 platform 承载。

### Requirement: Admin revoke on behalf of a user
**Reason**: platform 不再管理工具凭证吊销。
**Migration**: 删除管理员代吊销入口。

### Requirement: Offboarding linkage visibility
**Reason**: 旧工具凭证链路已移出 platform。
**Migration**: 删除相关离场视图和端点。

### Requirement: Credential lifecycle observability
**Reason**: platform 不再统计旧工具凭证生命周期。
**Migration**: 删除相关观测端点。

### Requirement: Sensitive value masking across all views
**Reason**: 相关视图已移除。
**Migration**: 无单独控制面序列化层保留。

### Requirement: OAuth connectors managed natively in the React SPA
**Reason**: React SPA 中对应页面与导航已删除。
**Migration**: OAuth connectors 的前端管理面不再存在；MCP 管理保留在独立方向。
