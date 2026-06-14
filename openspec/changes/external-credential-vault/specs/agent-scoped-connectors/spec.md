# agent-scoped-connectors Specification

## REMOVED Requirements

### Requirement: Connector ownership by agent

**Reason**: 该 per-agent connector 覆盖层为 dormant 死代码——`connectors.agent_id` 列自迁移 040 起从未被写入非 NULL 值，所有 admin 写入路径恒为全局 scope，overlay 解析分支从未生效。随 `connectors`→`external_services` 重塑为**单层全局**服务注册表，该维度移除。

**Migration**: `connectors.agent_id` 列、`ux_connectors_agent_scope` / `ux_connectors_global_scope` partial 索引、store 的 overlay 解析分支一并删除；每个 `service_id` 在 `external_services` 中仅一条全局记录。per-principal 的差异化由 `external_credentials`（按 `(user_id, service_id)`）承载，不再由 per-agent connector 行承载。

### Requirement: Connector credential resolution is scoped by agent

**Reason**: 凭证隔离轴从「per-agent connector scope」改为「per-principal（`external-credential-vault`）」。凭证按 `(user_id, service_id)` 隔离、由 `agent_service_grants.run_as` 决定取调用用户还是 agent principal 的凭证，per-agent connector 覆盖层不再是隔离机制。

**Migration**: 凭证解析改由 Vault provider 经 `connectors.get_credential(user_id, service, scopes)` 按 principal 进行（见 `external-credential-vault`）；`client_secret` 仍永不入库（走 env / `agent_secrets`）。

## MODIFIED Requirements

### Requirement: Admin surfaces expose the owning agent

The admin face SHALL display the owning agent for each entry in the MCP server list, and SHALL support filtering the MCP server list by agent. Global-default MCP server entries SHALL be shown distinctly from agent-owned entries. 外部服务注册表（`external_services`）为单层全局、无 owning-agent 维度，故其目录与 per-user 授权视图 SHALL NOT 再展示或按 owning agent 过滤。

#### Scenario: MCP server list shows owner
- **WHEN** an admin opens the MCP server list
- **THEN** each server entry shows its owning agent, or "global default" for entries
  authored without an agent scope

#### Scenario: 外部服务目录无 owning-agent 维度
- **WHEN** an admin opens the external services directory
- **THEN** entries are listed as a single global registry with no owning-agent column and no by-agent filter
