## ADDED Requirements

### Requirement: Integrations package migration
系统 SHALL 将外部能力接入实现迁入 `fleetent.integrations` package，并保持 legacy 顶层 import 路径兼容。

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

#### Scenario: Legacy MCP import remains compatible
- **WHEN** 调用方导入 `fleetent.mcp_client`
- **THEN** 导入成功
- **AND** 旧路径暴露迁移前 MCP public API

#### Scenario: Legacy sandbox import remains compatible
- **WHEN** 调用方导入 `fleetent.sandbox_client`
- **THEN** 导入成功
- **AND** 旧路径暴露迁移前 sandbox public API

#### Scenario: Integrations shims do not contain business logic
- **WHEN** 查看 legacy 顶层 `mcp_client.py` 或 `sandbox_client.py`
- **THEN** 文件只 re-export `fleetent.integrations.*` 的 public names
- **AND** 不创建 MCP session
- **AND** 不创建 Docker subprocess
- **AND** 不承载业务逻辑或 module-level runtime state

#### Scenario: Runtime and server use integrations through public API
- **WHEN** server 注册 MCP servers 或 tools 创建 sandbox client
- **THEN** 它们通过 `fleetent.integrations` public API 调用外部能力接入
- **AND** integrations package 不反向 import agent runtime entrypoint
