## REMOVED Requirements

### Requirement: Per-agent OAuth connector binding store
**Reason**: 退役工具 OAuth Vault——`agent_service_grants` 绑定 store 随 `external_services` / `external_credentials` 一并退役（零生产工具消费）。
**Migration**: drop `agent_service_grants`（Alembic 108）；删 legacy grant store 及 oauth-binding re-export shim。agent↔外部服务的授权关系改由 agent 侧实现。

### Requirement: Admin 授权 agent 使用服务并设置 run_as
**Reason**: 随 `agent_service_grants` 退役；`run_as` grant 概念（user/agent 凭证身份切换）随表删除。
**Migration**: 删 `/admin/agents/{name}/bindings/oauth*` 端点。注意：此 `run_as` 仅指 vault grant 维度，与 sandbox 的 `run_as`（同名异义）无关，后者不动。`connectors.py` 的 `get_credential(agent_name=...)` 签名保留为将来 agent 侧 run_as 留口，但平台不再解析。

### Requirement: run_as=agent 解析生效
**Reason**: 随 vault provider 的 principal 解析退役。
**Migration**: `run_as=agent` 时铸造/取用 agent service-principal 凭证的解析随平台 provider 删除。`agent-service-principal` 身份机制本身（被 user_store/agent_store 消费）**不在本 change 范围**、保留不动。
