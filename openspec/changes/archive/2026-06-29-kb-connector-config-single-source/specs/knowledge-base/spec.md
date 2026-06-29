## MODIFIED Requirements

### Requirement: Connector configuration registry
系统 SHALL 从**注入的、源自 platform `kb_connector_store`（`kb_connectors` 表）的** connector 定义中加载 knowledge-base connector，并以 `connector_id` 提供稳定查找入口。connector operations SHALL NOT 在缺省 settings 时隐式读取 YAML 应用配置来发现 connector;connector 定义的单一真相源为 `kb_connector_store`，由 platform 控制面读取并注入,单机无 platform 时由 ingest CLI 从本地来源显式注入。

#### Scenario: Connectors load from injected store-sourced settings
- **WHEN** platform 经 `kb_connector_store.as_knowledge_base_settings()` 注入 connector 定义
- **THEN** 系统把每条配置解析为对应的 Google Drive / Confluence connector config

#### Scenario: No implicit YAML connector discovery
- **WHEN** 调用 connector 列举 / 查找 operation 而未注入 settings
- **THEN** 系统不回落到 `load_knowledge_config()` 从 YAML 发现 connector
- **AND** 系统要求显式注入的 settings 来源

#### Scenario: Connector ids are globally unique
- **WHEN** 两个 connector 使用相同 `connector_id`
- **THEN** registry fail fast

#### Scenario: Disabled connectors are listed but not synced
- **WHEN** connector 配置 `enabled=false`
- **THEN** list 操作仍显示该 connector
- **AND** sync 操作返回 disabled 状态且不访问 remote API
