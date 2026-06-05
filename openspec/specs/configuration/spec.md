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

敏感值 SHALL 继续通过环境变量或 `.env` 注入,而不是写入 `config/settings.yaml` 或 `agent.yaml`。IM
tokens(`slack_bot_token`、`slack_app_token`、`telegram_bot_token`)MUST NOT 作为 `Settings` 字段存在——
IM 凭证经 per-agent `connectors` 的 `*_env` 引用提供。

#### Scenario: Secret references use env names
- **WHEN** 某 provider 需要 API key
- **THEN** 配置文件只保存 `api_key_env` 或等价 env var 名称,不保存 secret value

#### Scenario: IM tokens are not Settings fields
- **WHEN** 构造 `Settings`
- **THEN** 不存在 `slack_bot_token` / `slack_app_token` / `telegram_bot_token` 字段
- **AND** IM 凭证经 agent.yaml `connectors.*` 的 `*_env` 引用提供

#### Scenario: Settings example is not required for deployed agent
- **WHEN** 查看部署模板
- **THEN** `config/settings.yaml.example` 不需要存在
- **AND** 部署 agent 的非敏感示例配置位于 `config/agent.yaml.example`

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

全局 `Settings` SHALL 收缩为**平台控制面所需的精简集**:`database_url`(平台 authoring/control-plane DB,
与 per-agent home 推导出的运行时 DB 分离)、平台进程日志(`log_format`、`observability`)及必要的平台
密钥引用。agent 运行时配置(治理、部署、智能层 namespace)MUST NOT 出现在 `config/settings.yaml`——这些
已收口到对应 agent 的 `agent.yaml`。

#### Scenario: Supported settings fields
- **WHEN** 构造 `Settings` 并查看其字段
- **THEN** `Settings` 只暴露 `database_url`、`log_format`、`observability`
- **AND** `database_url` 默认推导为 home 下的 `sqlite:///<data_dir>/fleetent.db`
- **AND** 全局 `config/settings.yaml.example` 模板不再随仓库发布(`drop-global-config-files`),
  部署 agent 自包含于 `agent.yaml` + `.env`

#### Scenario: Agent-runtime namespaces are absent from Settings
- **WHEN** 构造 `Settings`
- **THEN** 不存在 `vector_store`、`embedding`、`rerank`、`knowledge_base`、`long_term_ctx`、`mcp`、
  `scheduling`、`webhooks`、`diagnostics` 字段,也不存在任何治理/部署旋钮
- **AND** 这些配置位于对应 agent 的 `agent.yaml`

#### Scenario: Runtime objects stay out of settings
- **WHEN** 加载 `config/settings.yaml`(若存在)
- **THEN** 只解析 `database_url`、`log_format`、`observability`;cron jobs、webhook sources、
  MCP server definitions、agent definitions、user bindings、memory items、knowledge documents 或
  reindex jobs 一律不在此承载

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
agent 运行时 SHALL 在 `settings.yaml` / `mcp.yaml` / `mcp.servers.yaml` 缺失时回退到内置默认值，不得因其缺失而启动失败。这三个全局配置文件 SHALL NOT 作为部署/脚手架的默认产物（install.sh 部署扁平 home，`init-config` 不再 seed 它们）。仓库示例模板按使用方分目录：`config/agent/`（agent.yaml + agent 的 .env）与 `config/platform/`（平台 .env）。

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

#### Scenario: Example templates split by component under config/
- **WHEN** 查看仓库 `config/`
- **THEN** 不存在 `settings.yaml.example` / `mcp.yaml.example` / `mcp.servers.yaml.example`，也不存在仓库根 `.env.example`
- **AND** 存在 `config/agent/agent.yaml.example` 与 `config/agent/.env.example`（部署 agent 模板）
- **AND** 存在 `config/platform/.env.example`（平台模板）

### Requirement: Vector provider config uses env references
Embedding and rerank HTTP provider configuration SHALL support environment-variable references for deploy-time provider values while keeping secrets out of tracked YAML.

#### Scenario: Embedding HTTP provider env references
- **WHEN** `settings.yaml` configures `embedding.backend: http`
- **THEN** endpoint, model, and dimensions may be supplied through `endpoint_env`, `model_env`, and `dimensions_env`
- **AND** the API key is supplied through `api_key_env`
- **AND** direct literal `endpoint`, `model`, and `dimensions` fields remain compatible

#### Scenario: Rerank HTTP provider env references
- **WHEN** `settings.yaml` configures `rerank.backend: http`
- **THEN** endpoint and model may be supplied through `endpoint_env` and `model_env`
- **AND** the API key is supplied through `api_key_env`
- **AND** direct literal `endpoint` and `model` fields remain compatible

#### Scenario: Templates expose smoke env names without secrets
- **WHEN** operator views `.env.example`
- **THEN** the file shows the env var names used by real embedding and rerank smoke
- **AND** the file does not contain provider API key values

