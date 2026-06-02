## ADDED Requirements

### Requirement: Diagnostics configuration
系统 SHALL 提供 diagnostics 配置 namespace，用于控制诊断导出目录和手动 retention 策略。

#### Scenario: Diagnostics defaults are conservative
- **WHEN** 未显式配置 diagnostics
- **THEN** `diagnostics.export_dir` 默认为 `data/diagnostics`
- **AND** `diagnostics.retention.enabled` 默认为 false
- **AND** logs、traces 和 diagnostic exports 的 retention days 默认为空

#### Scenario: Retention days are opt-in
- **WHEN** `diagnostics.retention.enabled=true`
- **AND** 某个 retention days 字段为空
- **THEN** 系统不清理该数据类型

#### Scenario: Settings example includes diagnostics without default deletion
- **WHEN** 查看 `config/settings.yaml.example`
- **THEN** 文件包含 diagnostics 配置示例
- **AND** retention 默认 disabled
- **AND** retention days 字段为空或未设置

#### Scenario: Diagnostics config contains no secrets
- **WHEN** 查看 diagnostics 配置
- **THEN** 配置不包含 token、API key、password、secret 或 credential payload
