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
- **THEN** 配置包含 connector_id、enabled、tenant_id、kb_id、folder_id 和 recursive
- **AND** OAuth credential 字段通过 `access_token_env`、`refresh_token_env`、`client_id_env` 和
  `client_secret_env` 引用环境变量
- **AND** Google token URI 使用代码默认值

#### Scenario: Confluence connector config shape
- **WHEN** `settings.yaml` 配置 Confluence connector
- **THEN** 配置包含 connector_id、enabled、tenant_id、kb_id、base_url、scope 字段、`username_env` 和
  `api_token_env`

#### Scenario: Config stores credential env references only
- **WHEN** `settings.yaml` 配置任意 knowledge-base connector
- **THEN** 配置只包含 env var name references
- **AND** 不包含 OAuth refresh token、client secret、Confluence API token 或其他真实 credential payload

#### Scenario: Legacy credential ref remains compatible
- **WHEN** connector 仍配置 legacy `credential_ref`
- **THEN** 系统保持兼容，不要求 operator 立即迁移已有本地配置

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

### Requirement: Credential references use flat environment examples
配置样例 SHALL 使用平铺环境变量引用展示 connector credential，不要求 operator 把 OAuth JSON 放入单个环境变量或文件路径。

#### Scenario: Google Drive config uses explicit env fields
- **WHEN** operator 查看 `config/settings.yaml.example`
- **THEN** Google Drive 示例显式使用 `access_token_env`、`refresh_token_env`、`client_id_env` 和
  `client_secret_env`

#### Scenario: Confluence username uses env reference
- **WHEN** operator 查看 `config/settings.yaml.example`
- **THEN** Confluence 示例使用 `username_env`
- **AND** token 使用 `api_token_env`

#### Scenario: Credential ref does not encode scope in filename
- **WHEN** operator 查看配置样例和 secrets 文档
- **THEN** secret 文件名不使用 `eng`、`product` 或类似 connector scope 作为命名要求

### Requirement: Global config files are optional
agent 运行时 SHALL 在 `settings.yaml` / `mcp.yaml` / `mcp.servers.yaml` 缺失时回退到内置默认值，不得因其缺失而启动失败。这三个全局配置文件 SHALL NOT 作为部署/脚手架的默认产物（install.sh 部署扁平 home，`init-config` 不再 seed 它们）。

#### Scenario: Settings falls back to defaults without settings.yaml
- **WHEN** `settings.yaml` 不存在
- **THEN** `Settings` 使用类型化默认值（env/.env 仍可覆盖）
- **AND** 不抛错

#### Scenario: MCP works without global mcp files
- **WHEN** `mcp.yaml` 与 `mcp.servers.yaml` 均不存在
- **THEN** 全局 MCP 文件注册为空（per-agent agent.yaml 的 `mcp_servers` 与 admin DB 仍生效）
- **AND** 启动不报错

#### Scenario: init-config does not seed global config files
- **WHEN** operator 运行 `fleetent-admin init-config`
- **THEN** 不创建 `config/settings.yaml` 或 `config/mcp.servers.yaml`
- **AND** 仍创建 `.env` 与数据目录

#### Scenario: Global example templates are absent from the repo
- **WHEN** 查看仓库 `config/`
- **THEN** 不存在 `settings.yaml.example` / `mcp.yaml.example` / `mcp.servers.yaml.example`
- **AND** 存在 `config/agent.yaml.example`（部署 agent 的模板）

