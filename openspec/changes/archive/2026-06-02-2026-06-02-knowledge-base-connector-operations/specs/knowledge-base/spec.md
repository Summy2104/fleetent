## ADDED Requirements

### Requirement: Connector configuration registry
系统 SHALL 从非 secret 应用配置中加载 knowledge-base connector 定义，并以 `connector_id` 提供稳定查找入口。

#### Scenario: Google Drive connectors load from settings
- **WHEN** `settings.yaml` 包含 `knowledge_base.google_drive.connectors`
- **THEN** 系统可以把每条配置解析为 Google Drive connector config

#### Scenario: Confluence connectors load from settings
- **WHEN** `settings.yaml` 包含 `knowledge_base.confluence.connectors`
- **THEN** 系统可以把每条配置解析为 Confluence connector config

#### Scenario: Connector ids are globally unique
- **WHEN** 两个 connector 使用相同 `connector_id`
- **THEN** registry fail fast

#### Scenario: Disabled connectors are listed but not synced
- **WHEN** connector 配置 `enabled=false`
- **THEN** list 操作仍显示该 connector
- **AND** sync 操作返回 disabled 状态且不访问 remote API

### Requirement: Connector operations public API
系统 SHALL 提供 knowledge-base connector operations public API，用于列出、检查、同步和查看最近一次状态。

#### Scenario: Connector operations API is importable
- **WHEN** 调用方从 `fleetent.intelligence.knowledge_base` 导入 connector operations dataclasses 和 functions
- **THEN** 导入成功

#### Scenario: List connectors returns safe summaries
- **WHEN** 调用 connector list operation
- **THEN** 返回 connector_id、type、enabled、tenant_id、kb_id 和 scope 摘要
- **AND** 不返回真实 credential payload

#### Scenario: Unknown connector fails clearly
- **WHEN** 对不存在的 `connector_id` 调用 check、sync 或 status operation
- **THEN** 系统返回明确的 not-found 错误

### Requirement: Connector credential and scope check
系统 SHALL 支持对 connector 的 `credential_ref` 和 remote scope 执行显式检查。

#### Scenario: Missing credential is reported
- **WHEN** `credential_ref` 指向不存在的文件或未设置的环境变量
- **THEN** check operation 返回 `credential_missing`

#### Scenario: Invalid credential is reported
- **WHEN** `credential_ref` 可读取但格式非法
- **THEN** check operation 返回 `credential_invalid`

#### Scenario: Auth failure is reported
- **WHEN** connector client 认证失败
- **THEN** check operation 返回 `auth_failed`

#### Scenario: Scope unreachable is reported
- **WHEN** connector client 无法访问配置的 folder、space 或 page scope
- **THEN** check operation 返回 `scope_unreachable`

#### Scenario: Check result is sanitized
- **WHEN** check operation 返回失败详情
- **THEN** 结果不包含 token、secret、credential payload 或完整文档正文

### Requirement: Connector sync dry-run
系统 SHALL 支持 connector sync dry-run，用于生成同步计划而不修改 KB 数据。

#### Scenario: Dry-run does not mutate knowledge data
- **WHEN** 调用 connector sync dry-run
- **THEN** 系统生成 plan summary
- **AND** 不写入 `knowledge_documents`
- **AND** 不写入 `knowledge_source_states`
- **AND** 不写入 vector_store

#### Scenario: Dry-run records dry-run status
- **WHEN** connector sync dry-run 完成
- **THEN** 系统更新该 connector 的最近一次状态为 dry-run 结果
- **AND** 状态不会被标记为真实 sync 成功

### Requirement: Connector sync operation
系统 SHALL 支持通过 connector operations 执行手动同步，并保存最近一次同步摘要。

#### Scenario: Sync runs matching connector executor
- **WHEN** 调用 connector sync operation
- **THEN** 系统根据 connector type 调用对应 Google Drive 或 Confluence sync executor

#### Scenario: Sync status summary is persisted
- **WHEN** connector sync 完成
- **THEN** 系统保存 scanned、planned、ingested、changed、unchanged、unsupported、archived、failed 和 auth_failed 计数

#### Scenario: Sync failure still records status
- **WHEN** connector sync 失败
- **THEN** 系统保存失败状态和脱敏错误摘要
- **AND** 后续 status 查询可返回该失败状态

### Requirement: Connector status persistence
系统 SHALL 保存每个 connector 最近一次运行状态，不保存完整运行历史。

#### Scenario: Status table exists
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 knowledge-base-owned `knowledge_connector_status` 表

#### Scenario: Only latest status is kept
- **WHEN** 同一 connector 多次写入 status
- **THEN** status 查询只返回最近一次结果

#### Scenario: Never-run status is stable
- **WHEN** connector 存在但从未执行 check、dry-run 或 sync
- **THEN** status operation 返回 `never_run`

#### Scenario: Status payload is sanitized
- **WHEN** status 包含 summary 或 error
- **THEN** 持久化内容不包含 token、secret、credential payload 或完整文档正文

### Requirement: Admin CLI connector operations
系统 SHALL 在 `fleetent-admin` 中提供 knowledge-base connector operations 命令。

#### Scenario: List connectors from CLI
- **WHEN** operator 运行 `fleetent-admin kb connectors list`
- **THEN** CLI 输出配置的 connector 摘要

#### Scenario: Check connector from CLI
- **WHEN** operator 运行 `fleetent-admin kb connectors check <connector_id>`
- **THEN** CLI 输出该 connector 的检查状态

#### Scenario: Show connector status from CLI
- **WHEN** operator 运行 `fleetent-admin kb connectors status <connector_id>`
- **THEN** CLI 输出该 connector 最近一次状态或 `never_run`

#### Scenario: Dry-run sync from CLI
- **WHEN** operator 运行 `fleetent-admin kb connectors sync <connector_id> --dry-run`
- **THEN** CLI 执行 dry-run 并输出 plan summary

#### Scenario: Run sync from CLI
- **WHEN** operator 运行 `fleetent-admin kb connectors sync <connector_id>`
- **THEN** CLI 执行真实 sync 并输出 sync summary

#### Scenario: CLI output is sanitized
- **WHEN** CLI 输出 connector check、sync 或 status 结果
- **THEN** 输出不包含 token、secret、credential payload 或完整文档正文
