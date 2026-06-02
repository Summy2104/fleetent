## MODIFIED Requirements

### Requirement: Unified settings file
系统 SHALL 使用 `config/settings.yaml` 作为唯一非敏感应用配置文件。

#### Scenario: Settings loaded from YAML
- **WHEN** `config/settings.yaml` 存在并包含 typed settings 字段
- **THEN** `Settings()` 使用这些值构造配置对象

#### Scenario: Missing settings file uses defaults
- **WHEN** `config/settings.yaml` 不存在
- **THEN** `Settings()` 使用代码中的 typed defaults
- **AND** 默认 database_url 为 `sqlite:///data/fleetent.db`

#### Scenario: Environment overrides YAML
- **WHEN** 同一配置同时存在于 `config/settings.yaml` 和环境变量
- **THEN** 环境变量值优先

### Requirement: Minimal settings surface
第一版统一配置 SHALL 只包含当前明确需要的顶层 namespace。

#### Scenario: Supported settings namespaces
- **WHEN** 查看 `config/settings.yaml.example`
- **THEN** 文件只包含 database_url、log_format、observability、mcp、scheduling、webhooks、
  vector_store、embedding、rerank、knowledge_base 和 long_term_ctx
- **AND** database_url 示例值为 `sqlite:///data/fleetent.db`

#### Scenario: Runtime objects stay out of settings
- **WHEN** 查看 `config/settings.yaml.example`
- **THEN** 文件不包含 cron jobs、webhook sources、MCP server definitions、agent definitions、
  user bindings、memory items、knowledge documents 或 reindex jobs

#### Scenario: MCP settings are global policy only
- **WHEN** 查看 `config/settings.yaml.example`
- **THEN** `mcp` namespace 只包含全局策略字段，不包含 `servers`
