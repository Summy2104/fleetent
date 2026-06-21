## ADDED Requirements

### Requirement: Diagnostics and retention deployment guidance
部署文档 SHALL 说明 Pilot 环境中的 diagnostics export 和手动 retention 操作边界。

#### Scenario: Diagnostics export is documented
- **WHEN** operator 阅读 deployment 文档
- **THEN** 文档说明如何运行 `fleetent admin diagnostics export`
- **AND** 文档说明诊断包包含和不包含的内容

#### Scenario: Retention default is documented
- **WHEN** operator 阅读 deployment 文档
- **THEN** 文档说明默认不设置保留时长
- **AND** 默认不自动清理

#### Scenario: Manual retention is documented
- **WHEN** operator 阅读 deployment 文档
- **THEN** 文档说明如何运行 `fleetent admin diagnostics retention dry-run`
- **AND** 文档说明只有显式开启 `diagnostics.retention.enabled=true` 后 apply 才会删除诊断数据

#### Scenario: Backup deletion is out of scope
- **WHEN** operator 阅读 deployment 文档
- **THEN** 文档说明 diagnostics retention 不删除 SQLite backups
- **AND** 数据库备份保留策略由部署方单独管理
