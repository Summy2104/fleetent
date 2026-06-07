# configuration Specification

## Purpose
TBD - created by archiving change configuration-foundation. Update Purpose after archive.
## Requirements
### Requirement: Secrets stay outside config YAML

敏感值 SHALL 继续通过环境变量或 `.env` 注入,而不是写入 `platform.yaml` 或 `agent.yaml`。IM
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
- **AND** 默认部署 agent 的非敏感示例配置位于 `agents/default/agent.yaml.example`

### Requirement: Local configuration initialization

系统 SHALL 提供 `fleetent-admin init-config` 作为 Platform home 配置初始化入口。

#### Scenario: Init config creates local Platform files
- **WHEN** operator 运行 `fleetent-admin init-config`
- **THEN** 系统从 `.env.example` 创建 `.env`
- **AND** 从 `platform.yaml.example` 创建 `platform.yaml`
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
- **THEN** 系统覆盖 `.env` 和 `platform.yaml`
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

### Requirement: Vector provider config uses env references
Embedding and rerank HTTP provider configuration SHALL support environment-variable references for deploy-time provider values while keeping secrets out of tracked YAML.

#### Scenario: Embedding HTTP provider env references
- **WHEN** Agent or Platform model config declares an HTTP embedding provider
- **THEN** endpoint, model, and dimensions may be supplied through `endpoint_env`, `model_env`, and `dimensions_env`
- **AND** the API key is supplied through `api_key_env`
- **AND** direct literal `endpoint`, `model`, and `dimensions` fields remain compatible

#### Scenario: Rerank HTTP provider env references
- **WHEN** Agent or Platform model config declares an HTTP rerank provider
- **THEN** endpoint and model may be supplied through `endpoint_env` and `model_env`
- **AND** the API key is supplied through `api_key_env`
- **AND** direct literal `endpoint` and `model` fields remain compatible

#### Scenario: Templates expose smoke env names without secrets
- **WHEN** operator views `.env.example`
- **THEN** the file shows the env var names used by real embedding and rerank smoke
- **AND** the file does not contain provider API key values

### Requirement: Configuration is split by Platform and Agent perspective

配置 SHALL 按 Platform side 与 Agent side 两个视角组织。Platform home is the deployment root:
repo root in local development and `FLEETENT_HOME` in installed deployments. Platform side SHALL
own `.env`, `platform.yaml`, Platform DB, Agent authoring/deployment/materialize, and default
embedded platform capabilities such as Knowledge / Memory / Worker. Agent side SHALL own
`agents/<agent-id>/agent.yaml`, `agents/<agent-id>/.env`, and `agents/<agent-id>/data/`.

`config/` SHALL NOT be a current runtime config namespace, template namespace, or fallback
namespace.

#### Scenario: Platform home has root config files
- **WHEN** 查看一个 Platform home
- **THEN** Platform env instance is `.env`
- **AND** Platform non-secret config instance is `platform.yaml`
- **AND** Platform runtime does not require `config/`

#### Scenario: Agent home is self-contained
- **WHEN** 查看一个已 materialize 的 Agent home
- **THEN** 它包含 `agent.yaml`、`.env` 和 `data/`
- **AND** `agent.yaml` 只含非敏感配置与 env 引用
- **AND** `.env` 只含该 Agent runtime 所需变量

### Requirement: Platform env and Agent env are separate

The system SHALL keep Platform process environment variables separate from Agent runtime
environment variables.

`FLEETENT_SECRET_KEY`、`DATABASE_URL`、平台日志、TUI token、embedded Platform service credentials
等平台进程变量 SHALL belong to Platform `.env`. Model provider key、Agent IM token、Agent MCP
secret、Agent-local runtime secret 等 Agent runtime variables SHALL belong to
`agents/<agent-id>/.env`.

#### Scenario: Platform env template contains only Platform variables
- **WHEN** 读取 `.env.example`
- **THEN** 它包含 Platform process variables such as `FLEETENT_SECRET_KEY` and `DATABASE_URL`
- **AND** 不包含 Agent model / Slack / MCP runtime secret placeholders

#### Scenario: Agent required env is materialized
- **WHEN** 一个 Agent 引用 model / MCP / connector secret env
- **THEN** materialize 在 `agents/<agent-id>/.env` 中写入对应 env 名和值或空占位
- **AND** 不写入 `FLEETENT_SECRET_KEY`、`DATABASE_URL` 或 Platform-owned KB construction env

### Requirement: Canonical templates avoid ambiguous agent paths

Repository examples SHALL live beside the runtime files they template. The repository SHALL provide
exactly these canonical config examples:

- `.env.example`
- `platform.yaml.example`
- `agents/default/agent.yaml.example`
- `agents/default/.env.example`

The repository SHALL NOT use `config/` as a deployment template namespace and SHALL NOT ship extra
Agent config/env examples under `agents/default/` that do not map one-to-one to runtime files.

The four canonical examples SHALL be comprehensive references, not minimal skeletons. They MUST include
all currently supported non-secret fields for their runtime file and all env key references used by the
paired YAML example.

#### Scenario: Root Platform examples are discoverable
- **WHEN** 查看仓库配置模板
- **THEN** 存在 `.env.example`
- **AND** 存在 `platform.yaml.example`
- **AND** 不需要通过 `config/` 理解 Platform 配置

#### Scenario: Default Agent examples live with default Agent home
- **WHEN** 查看默认 Agent 模板
- **THEN** 存在 `agents/default/agent.yaml.example`
- **AND** 存在 `agents/default/.env.example`
- **AND** 不存在 `agents/default/.env.standalone.example`
- **AND** 不存在 `agents/default/agent.configure.yaml.example`
- **AND** 不存在 `agents/default/agent.defaults.yaml.example`

#### Scenario: Config directory is absent
- **WHEN** 查看仓库根目录
- **THEN** `config/` 不存在

#### Scenario: Agent YAML example covers the Agent schema
- **WHEN** `agents/default/agent.yaml.example` is parsed
- **THEN** it validates as an `AgentFile`
- **AND** every supported `AgentFile` field is present in the example unless the field is explicitly
  documented as generated-only or internal-only

#### Scenario: Agent env example covers Agent YAML env refs
- **WHEN** env references are extracted from `agents/default/agent.yaml.example`
- **THEN** every referenced env key exists in `agents/default/.env.example`
- **AND** `agents/default/.env.example` does not point operators to deleted noncanonical env examples

#### Scenario: Platform examples cover Platform env refs
- **WHEN** env references are extracted from `platform.yaml.example`
- **THEN** every referenced env key exists in `.env.example`
- **AND** `.env.example` contains Platform process env keys such as `FLEETENT_SECRET_KEY` and
  `DATABASE_URL`

#### Scenario: Platform YAML example validates
- **WHEN** `platform.yaml.example` is parsed by Platform config / embedded Knowledge config loaders
- **THEN** it validates without relying on any file under `config/`

### Requirement: Platform dotenv is home-scoped

Platform settings SHALL load Platform env values from `$FLEETENT_HOME/.env` / repo-root `.env`
using the same Platform home resolution as `platform.yaml`. External process environment variables
MUST take precedence over values in that dotenv file.

#### Scenario: Platform dotenv follows FLEETENT_HOME
- **WHEN** `FLEETENT_HOME=/srv/fleetent`
- **AND** `/srv/fleetent/.env` defines `DATABASE_URL=sqlite:////srv/fleetent/data/fleetent.db`
- **THEN** `Settings().database_url` uses that value even if the current working directory differs

#### Scenario: External env overrides Platform dotenv
- **WHEN** `$FLEETENT_HOME/.env` defines `DATABASE_URL=sqlite:///from-dotenv.db`
- **AND** the process environment defines `DATABASE_URL=sqlite:///from-process.db`
- **THEN** `Settings().database_url` is `sqlite:///from-process.db`
