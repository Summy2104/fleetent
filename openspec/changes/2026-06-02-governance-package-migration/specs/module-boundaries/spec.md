## ADDED Requirements

### Requirement: Governance package migration
系统 SHALL 将治理域实现迁入 `fleetent.governance` package，并保持 legacy 顶层 import 路径兼容。

#### Scenario: Governance package exists
- **WHEN** 调用方导入 `fleetent.governance`
- **THEN** 导入成功

#### Scenario: Governance canonical modules exist
- **WHEN** 调用方导入 `fleetent.governance.permission_gate`、`fleetent.governance.quota`、`fleetent.governance.audit_log`、`fleetent.governance.blocklist` 或 `fleetent.governance.agent_policy`
- **THEN** 导入成功

#### Scenario: Legacy governance imports remain compatible
- **WHEN** 调用方导入 `fleetent.permission_gate`、`fleetent.quota`、`fleetent.audit_log`、`fleetent.blocklist` 或 `fleetent.agent_policy`
- **THEN** 导入成功
- **AND** 旧路径暴露迁移前的 public API

#### Scenario: Governance shims do not contain business logic
- **WHEN** 查看 legacy 顶层 governance 文件
- **THEN** 文件只 re-export `fleetent.governance.*` 的 public names
- **AND** 不访问数据库
- **AND** 不读取配置
- **AND** 不承载业务逻辑

#### Scenario: Governance owns existing governance data responsibilities
- **WHEN** quota、audit log 或 blocklist 访问既有持久化数据
- **THEN** 该访问由 `fleetent.governance` package 内的实现负责
- **AND** 本 change 不新增数据库 schema

#### Scenario: Runtime uses governance through public API
- **WHEN** agent runtime 需要权限审批或工具访问策略
- **THEN** 它通过 `fleetent.governance` public API 调用治理能力
- **AND** governance package 不反向 import runtime entrypoint
