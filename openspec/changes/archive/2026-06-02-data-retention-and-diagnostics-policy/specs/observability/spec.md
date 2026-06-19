## ADDED Requirements

### Requirement: Diagnostics export
系统 SHALL 提供手动 diagnostics export，用于生成本地脱敏诊断包。

#### Scenario: Export creates package with manifest
- **WHEN** operator 运行 diagnostics export
- **THEN** 系统创建本地诊断包
- **AND** 包含 `manifest.json`

#### Scenario: Export includes diagnostic data
- **WHEN** operator 运行 diagnostics export
- **THEN** 诊断包可包含指定时间范围内的 structured logs、trace events 或 trace 摘要、usage summary、
  performance summary、connector status、environment summary 和 config summary

#### Scenario: Export excludes business data
- **WHEN** operator 运行 diagnostics export
- **THEN** 诊断包不包含 memory 内容、KB 文档正文、KB chunks、SQLite 主库、SQLite backups 或 connector credential 文件内容

#### Scenario: Export excludes full user content
- **WHEN** trace 或 log 中包含用户消息、prompt、reply 或工具 payload
- **THEN** 诊断包不包含完整原文
- **AND** 大文本被截断并带有截断标记

#### Scenario: Export performs second-pass redaction
- **WHEN** 诊断包写入 logs、traces、config summary 或 error summary
- **THEN** 系统再次脱敏 token、API key、password、secret、authorization、邮箱和手机号

### Requirement: Diagnostics retention planning
系统 SHALL 支持诊断数据 retention dry-run，用于展示将删除的候选但不修改数据。

#### Scenario: Dry-run identifies old logs
- **WHEN** 配置了 `diagnostics.retention.logs_days`
- **THEN** retention dry-run 返回超过天数的 log 文件候选

#### Scenario: Dry-run identifies old traces
- **WHEN** 配置了 `diagnostics.retention.traces_days`
- **THEN** retention dry-run 返回超过天数的 trace 记录数量

#### Scenario: Dry-run identifies old diagnostic exports
- **WHEN** 配置了 `diagnostics.retention.diagnostic_exports_days`
- **THEN** retention dry-run 返回超过天数的 diagnostics export 包候选

#### Scenario: Dry-run does not mutate
- **WHEN** operator 运行 retention dry-run
- **THEN** 系统不删除文件
- **AND** 不删除 trace 记录

### Requirement: Diagnostics retention apply
系统 SHALL 支持显式手动 retention apply，且只清理诊断数据。

#### Scenario: Apply disabled by default
- **WHEN** `diagnostics.retention.enabled=false`
- **AND** operator 运行 retention apply
- **THEN** 系统 fail fast
- **AND** 不删除任何文件或 trace 记录

#### Scenario: Apply deletes only configured old logs
- **WHEN** `diagnostics.retention.enabled=true`
- **AND** 配置了 `logs_days`
- **THEN** retention apply 只删除超过天数的 log 文件

#### Scenario: Apply deletes only configured old traces
- **WHEN** `diagnostics.retention.enabled=true`
- **AND** 配置了 `traces_days`
- **THEN** retention apply 只删除超过天数的 observability trace 记录

#### Scenario: Apply deletes only configured old exports
- **WHEN** `diagnostics.retention.enabled=true`
- **AND** 配置了 `diagnostic_exports_days`
- **THEN** retention apply 只删除超过天数的 diagnostics export 包

#### Scenario: Apply never deletes business data
- **WHEN** operator 运行 retention apply
- **THEN** 系统不删除 memory、KB documents、KB chunks、vector index、users、agents、schedules、connector source state、
  SQLite 主库或 SQLite backups

#### Scenario: Apply tolerates per-file deletion failure
- **WHEN** 删除某个诊断文件失败
- **THEN** 系统记录该失败
- **AND** 继续处理其他候选

### Requirement: Diagnostics admin CLI
系统 SHALL 在 `fleetent-admin` 中提供 diagnostics export 和 retention 手动操作命令。

#### Scenario: Export from CLI
- **WHEN** operator 运行 `fleetent admin diagnostics export`
- **THEN** CLI 调用 diagnostics export 并输出诊断包路径

#### Scenario: Retention dry-run from CLI
- **WHEN** operator 运行 `fleetent admin diagnostics retention dry-run`
- **THEN** CLI 输出将删除的诊断数据候选摘要
- **AND** 不删除任何数据

#### Scenario: Retention apply from CLI
- **WHEN** operator 运行 `fleetent-admin diagnostics retention apply`
- **THEN** CLI 执行手动 retention apply 或在 retention disabled 时返回非 0

#### Scenario: Diagnostics CLI output is sanitized
- **WHEN** CLI 输出 export、dry-run 或 apply 结果
- **THEN** 输出不包含 token、secret、credential payload 或完整文档正文
