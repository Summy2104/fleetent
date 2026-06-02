# configuration Specification

## Purpose
TBD - created by archiving change configuration-foundation. Update Purpose after archive.
## Requirements
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
- **AND** database_url 示例值为 `sqlite:///data/fleetent.db`

#### Scenario: Runtime objects stay out of settings
- **WHEN** 查看 `config/settings.yaml.example`
- **THEN** 文件不包含 cron jobs、webhook sources、MCP server definitions、agent definitions、
  user bindings、memory items、knowledge documents 或 reindex jobs

#### Scenario: MCP settings are global policy only
- **WHEN** 查看 `config/settings.yaml.example`
- **THEN** `mcp` namespace 只包含全局策略字段，不包含 `servers`

### Requirement: Knowledge-base connector configuration
系统 SHALL 支持在统一应用配置中声明 knowledge-base connector definitions，且只保存非 secret 字段和 credential references。

#### Scenario: Google Drive connector config shape
- **WHEN** `settings.yaml` 配置 Google Drive connector
- **THEN** 配置包含 connector_id、enabled、tenant_id、kb_id、folder_id、recursive 和 credential_ref

#### Scenario: Confluence connector config shape
- **WHEN** `settings.yaml` 配置 Confluence connector
- **THEN** 配置包含 connector_id、enabled、tenant_id、kb_id、base_url、username、scope 字段和 credential_ref

#### Scenario: Config stores credential reference only
- **WHEN** `settings.yaml` 配置任意 knowledge-base connector
- **THEN** 配置只包含 `credential_ref`
- **AND** 不包含 OAuth refresh token、client secret、Confluence API token 或其他真实 credential payload

#### Scenario: Credential ref supports file and env
- **WHEN** connector 配置 `credential_ref`
- **THEN** 系统支持 `file://...`、本地文件路径和 `env:VAR_NAME` 引用形式

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

### Requirement: Local configuration initialization
系统 SHALL 提供 `fleetent-admin init-config` 作为本地部署配置初始化入口。

#### Scenario: Init config creates local deployment files
- **WHEN** operator 运行 `fleetent-admin init-config`
- **THEN** 系统从 `.env.example` 创建 `.env`
- **AND** 从 `config/settings.yaml.example` 创建 `config/settings.yaml`
- **AND** 从 `config/mcp.servers.yaml.example` 创建 `config/mcp.servers.yaml`
- **AND** 创建 `data/`、`data/logs/`、`data/diagnostics/` 和 `secrets/`

#### Scenario: Init config does not overwrite by default
- **WHEN** 目标文件已经存在
- **AND** operator 未传 `--force`
- **THEN** init-config 跳过该文件
- **AND** 输出说明该文件已存在

#### Scenario: Init config dry run does not write
- **WHEN** operator 运行 `fleetent-admin init-config --dry-run`
- **THEN** 系统输出将创建、跳过或覆盖的路径
- **AND** 不写入文件系统

#### Scenario: Init config force overwrites generated files
- **WHEN** operator 运行 `fleetent-admin init-config --force`
- **THEN** 系统覆盖 `.env`、`config/settings.yaml` 和 `config/mcp.servers.yaml`
- **AND** 不删除未知文件
- **AND** 不生成任何真实 secret 文件

### Requirement: Env and secrets files stay out of git
本地 `.env` 和 `secrets/` SHALL 不进入版本控制；项目 SHALL only provide safe examples.

#### Scenario: Env example is versioned
- **WHEN** maintainer 查看仓库
- **THEN** `.env.example` 存在
- **AND** `.env` 被 git ignore
- **AND** `.env.example` 不包含真实 token、API key、password 或客户数据

#### Scenario: Secrets directory is ignored
- **WHEN** maintainer 查看仓库
- **THEN** `secrets/` 被 git ignore
- **AND** 仓库只提交 secrets 说明文档

#### Scenario: Secrets are deployment-level and flat
- **WHEN** operator 查看 secrets 说明文档
- **THEN** 文档说明 `secrets/` 目录平铺
- **AND** 示例文件名不包含 scope
- **AND** scope 由 connector config 或未来数据库配置表达

### Requirement: Credential references use container secrets path in examples
配置样例 SHALL 使用 Docker Compose mount 后的 `/app/secrets` 路径展示 file credential reference。

#### Scenario: Google Drive credential ref uses app secrets path
- **WHEN** operator 查看 `config/settings.yaml.example`
- **THEN** Google Drive 示例 `credential_ref` 使用 `file:///app/secrets/google-drive-token.json`

#### Scenario: Credential ref does not encode scope in filename
- **WHEN** operator 查看配置样例和 secrets 文档
- **THEN** secret 文件名不使用 `eng`、`product` 或类似 connector scope 作为命名要求
