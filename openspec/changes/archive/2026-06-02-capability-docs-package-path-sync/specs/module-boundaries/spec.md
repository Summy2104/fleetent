## ADDED Requirements

### Requirement: Capability docs use canonical package names
系统 SHALL 在当前架构文档和 capability docs 中使用已迁移模块的 canonical package 名称，而不是把已删除 legacy path 描述为主要实现位置或可用 public API。

#### Scenario: Current docs reference canonical memory package
- **WHEN** 读者查看当前 memory、long-term context、reflection 或 vector-store capability docs
- **THEN** 文档使用 `fleetent.intelligence.memory` 或 `intelligence.memory` 表示 User Memory public API

#### Scenario: Current docs reference canonical integrations packages
- **WHEN** 读者查看当前 MCP、sandbox、connectors 或 architecture docs
- **THEN** 文档使用 `fleetent.integrations.mcp` 和 `fleetent.integrations.sandbox` 表示外部能力接入实现

#### Scenario: Current docs reference canonical governance package
- **WHEN** 读者查看当前 governance、tools、IM gateway 或 platform capability docs
- **THEN** 文档使用 `fleetent.governance` 下的 public API 表示权限、审批、quota、audit 和 blocklist 能力

#### Scenario: Current docs reference canonical admin CLI entrypoint
- **WHEN** 读者查看当前 platform 或 architecture docs
- **THEN** 文档使用 `fleetent.platform.admin_cli` 或 `fleetent-admin` console script 表示 admin CLI 入口
- **AND** 不把 `fleetent.admin` 描述为当前实现入口

#### Scenario: Deleted legacy paths are not described as current APIs
- **WHEN** 当前 docs 描述 memory、governance、integrations 或 admin CLI
- **THEN** 文档不把已删除 legacy import path 描述为仍可用 public API

#### Scenario: Historical archive docs remain historical
- **WHEN** 搜索 `docs/archive/**` 或 `openspec/changes/archive/**`
- **THEN** 历史记录可以保留 legacy 模块名
- **AND** 本 change 不要求重写历史设计记录
