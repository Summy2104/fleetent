## ADDED Requirements

### Requirement: Unified settings file
系统 SHALL 使用 `config/settings.yaml` 作为唯一非敏感应用配置文件。

#### Scenario: Settings loaded from YAML
- **WHEN** `config/settings.yaml` 存在并包含 typed settings 字段
- **THEN** `Settings()` 使用这些值构造配置对象

#### Scenario: Missing settings file uses defaults
- **WHEN** `config/settings.yaml` 不存在
- **THEN** `Settings()` 使用代码中的 typed defaults

#### Scenario: Environment overrides YAML
- **WHEN** 同一配置同时存在于 `config/settings.yaml` 和环境变量
- **THEN** 环境变量值优先

### Requirement: Secrets stay outside settings YAML
敏感值 SHALL 继续通过环境变量或 `.env` 注入，而不是写入 `config/settings.yaml`。

#### Scenario: Secret references use env names
- **WHEN** 某 provider 需要 API key
- **THEN** YAML 只保存 `api_key_env` 或等价 env var 名称，不保存 secret value

#### Scenario: Settings example contains no real secrets
- **WHEN** 查看 `config/settings.yaml.example`
- **THEN** 文件不包含真实 token、API key、password 或客户数据

### Requirement: Legacy feature YAML files removed
系统 SHALL 不再读取 `config/mcp.yaml`、`config/cron.yaml` 或 `config/webhooks.yaml`。

#### Scenario: Old MCP config file is rejected
- **WHEN** `config/mcp.yaml` 存在
- **THEN** 启动 fail fast，并提示迁移到 `config/settings.yaml`

#### Scenario: Old cron config file is rejected
- **WHEN** `config/cron.yaml` 存在
- **THEN** 启动 fail fast，并提示 cron jobs 通过 SQLite-backed runtime management 创建

#### Scenario: Old webhook config file is rejected
- **WHEN** `config/webhooks.yaml` 存在
- **THEN** 启动 fail fast，并提示 webhook source management 后续通过 runtime API / store 管理

### Requirement: Minimal settings surface
第一版统一配置 SHALL 只包含当前明确需要的顶层 namespace。

#### Scenario: Supported settings namespaces
- **WHEN** 查看 `config/settings.yaml.example`
- **THEN** 文件只包含 database_url、log_format、observability、mcp、scheduling、webhooks、
  vector_store、embedding、rerank、knowledge_base 和 long_term_ctx

#### Scenario: Runtime objects stay out of settings
- **WHEN** 查看 `config/settings.yaml.example`
- **THEN** 文件不包含 cron jobs、webhook sources、agent definitions、user bindings、memory items、
  knowledge documents 或 reindex jobs
