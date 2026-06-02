## MODIFIED Requirements

### Requirement: Governance package migration
系统 SHALL expose governance implementation through `fleetent.governance` canonical package paths only;
legacy top-level governance shim modules SHALL NOT remain importable.

#### Scenario: Governance package exists
- **WHEN** 调用方导入 `fleetent.governance`
- **THEN** 导入成功

#### Scenario: Governance canonical modules exist
- **WHEN** 调用方导入 `fleetent.governance.permission_gate`、`fleetent.governance.quota`、`fleetent.governance.audit_log`、`fleetent.governance.blocklist` 或 `fleetent.governance.agent_policy`
- **THEN** 导入成功

#### Scenario: Legacy governance imports are removed
- **WHEN** 调用方导入 `fleetent.permission_gate`、`fleetent.quota`、`fleetent.audit_log`、`fleetent.blocklist` 或 `fleetent.agent_policy`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Governance owns existing governance data responsibilities
- **WHEN** quota、audit log 或 blocklist 访问既有持久化数据
- **THEN** 该访问由 `fleetent.governance` package 内的实现负责
- **AND** 本 change 不新增数据库 schema

#### Scenario: Platform and channels use governance public API
- **WHEN** platform 或 channels 模块需要 audit log、blocklist、quota 或 permission gate 能力
- **THEN** 它们通过 `fleetent.governance` canonical public API 调用
- **AND** legacy 顶层 shim 不存在

#### Scenario: Runtime uses governance through public API
- **WHEN** agent runtime 需要权限审批或工具访问策略
- **THEN** 它通过 `fleetent.governance` public API 调用治理能力
- **AND** governance package 不反向 import runtime entrypoint

### Requirement: Integrations package migration
系统 SHALL expose external capability integrations through `fleetent.integrations` canonical package paths
only; legacy top-level integrations shim modules SHALL NOT remain importable.

#### Scenario: Integrations package exists
- **WHEN** 调用方导入 `fleetent.integrations`
- **THEN** 导入成功

#### Scenario: MCP canonical package exists
- **WHEN** 调用方导入 `fleetent.integrations.mcp` 或 `fleetent.integrations.mcp.client`
- **THEN** 导入成功
- **AND** canonical path 暴露 MCP client public API

#### Scenario: Sandbox canonical package exists
- **WHEN** 调用方导入 `fleetent.integrations.sandbox` 或 `fleetent.integrations.sandbox.client`
- **THEN** 导入成功
- **AND** canonical path 暴露 sandbox client public API

#### Scenario: Legacy MCP import is removed
- **WHEN** 调用方导入 `fleetent.mcp_client`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Legacy sandbox import is removed
- **WHEN** 调用方导入 `fleetent.sandbox_client`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Runtime and server use integrations through public API
- **WHEN** server 注册 MCP servers 或 tools 创建 sandbox client
- **THEN** 它们通过 `fleetent.integrations` public API 调用外部能力接入
- **AND** integrations package 不反向 import agent runtime entrypoint
