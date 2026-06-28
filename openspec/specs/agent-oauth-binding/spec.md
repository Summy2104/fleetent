# agent-oauth-binding Specification

## Purpose
该能力已从 platform 侧退役；本 spec 记录其移除后的约束，避免旧授权模型被误接回控制面。

## REMOVED Requirements

### Requirement: Per-agent OAuth connector binding store
**Reason**: 退役工具 OAuth Vault，agent↔外部服务授权关系不再由 platform 管理。
**Migration**: drop `agent_service_grants`（Alembic 108）；删 legacy grant store 与 oauth-binding shim。未来若恢复该能力，应在 agent 侧重新设计。

### Requirement: Admin 授权 agent 使用服务并设置 run_as
**Reason**: platform 不再持有这类 grant，也不再暴露 agent OAuth 绑定管理面。
**Migration**: 删 `/admin/agents/{name}/bindings/oauth*` 端点。这里退役的仅是 vault grant 维度的 `run_as`，不影响 sandbox / agent config 中同名概念。

### Requirement: run_as=agent 解析生效
**Reason**: grant 已移除，platform 不再解析 agent/service-principal 方向的工具凭证。
**Migration**: 仅保留 `connectors.get_credential(..., agent_name=...)` 的 seam 形状，为将来 agent-side 方案留口。
