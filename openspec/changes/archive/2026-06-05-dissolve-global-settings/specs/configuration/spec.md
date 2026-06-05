## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: Knowledge-base connector configuration

**Reason**: knowledge-base connector 定义随智能层收口到 per-agent `agent.yaml`(`knowledge_base` 字段),
不再由全局 `settings.yaml` 承载。

**Migration**: 把 `settings.yaml` 中的 Google Drive / Confluence connector 定义迁到对应 agent 的
`agent.yaml` `knowledge_base` 块,credential 仍用 `*_env` / `credential_ref` 引用。

### Requirement: Diagnostics configuration

**Reason**: diagnostics(导出目录 + retention)属于 per-agent 部署旋钮,阶段 1 已纳入 `agent.yaml`,
阶段 2 runtime 已从 agent 配置读取,全局 `settings.yaml` 的 `diagnostics` namespace 不再需要。

**Migration**: 把 `settings.yaml` 的 `diagnostics` 配置迁到对应 agent 的 `agent.yaml` `diagnostics` 块。
