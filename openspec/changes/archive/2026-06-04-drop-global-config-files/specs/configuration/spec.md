## ADDED Requirements

### Requirement: Global config files are optional
agent 运行时 SHALL 在 `settings.yaml` / `mcp.yaml` / `mcp.servers.yaml` 缺失时回退到内置默认值，不得因其缺失而启动失败。这三个全局配置文件 SHALL NOT 作为部署/脚手架的默认产物（install.sh 部署扁平 home，`init-config` 不再 seed 它们）。

#### Scenario: Settings falls back to defaults without settings.yaml
- **WHEN** `settings.yaml` 不存在
- **THEN** `Settings` 使用类型化默认值（env/.env 仍可覆盖）
- **AND** 不抛错

#### Scenario: MCP works without global mcp files
- **WHEN** `mcp.yaml` 与 `mcp.servers.yaml` 均不存在
- **THEN** 全局 MCP 文件注册为空（per-agent agent.yaml 的 `mcp_servers` 与 admin DB 仍生效）
- **AND** 启动不报错

#### Scenario: init-config does not seed global config files
- **WHEN** operator 运行 `fleetent-admin init-config`
- **THEN** 不创建 `config/settings.yaml` 或 `config/mcp.servers.yaml`
- **AND** 仍创建 `.env` 与数据目录

#### Scenario: Global example templates are absent from the repo
- **WHEN** 查看仓库 `config/`
- **THEN** 不存在 `settings.yaml.example` / `mcp.yaml.example` / `mcp.servers.yaml.example`
- **AND** 存在 `config/agent.yaml.example`（部署 agent 的模板）
