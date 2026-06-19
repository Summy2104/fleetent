## MODIFIED Requirements

### Requirement: Configuration is split by Platform and Agent perspective

配置 SHALL 按 Platform side 与 Agent side 两个视角组织。Platform home is the deployment root:
repo root in local development and `FLEETENT_HOME` in installed deployments. Platform side SHALL
own `.env`, `platform.yaml`, Platform DB, Agent authoring/deployment/materialize, and default
embedded platform capabilities such as Knowledge / Memory / Worker. Agent side SHALL own
`agents/<agent-id>/agent.yaml`, `agents/<agent-id>/.env`, and `agents/<agent-id>/data/`.

#### Scenario: Platform home has root config files
- **WHEN** 查看一个 Platform home
- **THEN** Platform env instance is `.env`
- **AND** Platform non-secret config instance is `platform.yaml`
- **AND** Platform runtime does not require `config/platform/` or `config/settings.yaml`

#### Scenario: Agent home is self-contained
- **WHEN** 查看一个已 materialize 的 Agent home
- **THEN** 它包含 `agent.yaml`、`.env` 和 `data/`
- **AND** `agent.yaml` 只含非敏感配置与 env 引用
- **AND** `.env` 只含该 Agent runtime 所需变量

### Requirement: Canonical templates avoid ambiguous agent paths

Repository examples SHALL live beside the runtime files they template. The repository SHALL provide
root Platform examples `.env.example` and `platform.yaml.example`, and default Agent examples
`agents/default/agent.yaml.example` and `agents/default/.env.example`. The repository SHALL NOT use
`config/` as a canonical deployment template namespace.

#### Scenario: Root Platform examples are discoverable
- **WHEN** 查看仓库配置模板
- **THEN** 存在 `.env.example`
- **AND** 存在 `platform.yaml.example`
- **AND** 不需要通过 `config/platform/` 理解 Platform 配置

#### Scenario: Default Agent examples live with default Agent home
- **WHEN** 查看默认 Agent 模板
- **THEN** 存在 `agents/default/agent.yaml.example`
- **AND** 存在 `agents/default/.env.example`
- **AND** 不需要通过 `config/agent/` 理解 Agent 配置

#### Scenario: Config directory is not a template namespace
- **WHEN** 查看仓库根目录
- **THEN** `config/` 不包含 canonical `.example` 配置模板
- **AND** 不存在 `config/agent/`、`config/platform/`、`config/knowledge-service/` 或
  `config/knowledge.yaml.example` 作为当前部署模板

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

### Requirement: Local configuration initialization

系统 SHALL 提供 `fleetent admin init-config` 作为 Platform home 配置初始化入口。

#### Scenario: Init config creates local Platform files
- **WHEN** operator 运行 `fleetent admin init-config`
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

## REMOVED Requirements

### Requirement: Unified settings file

**Reason**: MVP Platform home now uses root `platform.yaml` plus `.env`; `config/settings.yaml`
is no longer the canonical non-secret config file.

**Migration**: Move Platform non-secret settings into `platform.yaml`; keep secrets in `.env`
or external secret injection.

### Requirement: Legacy feature YAML files removed

**Reason**: The old migration target `config/settings.yaml` is no longer canonical after the
Platform home layout change.

**Migration**: Keep feature configuration in Platform DB / `platform.yaml` or per-Agent
`agents/<agent-id>/agent.yaml`, depending on ownership.

### Requirement: Minimal settings surface

**Reason**: The minimal Platform settings surface is now represented by root `platform.yaml`
and environment, not by `config/settings.yaml`.

**Migration**: Use `platform.yaml` for Platform non-secret config and Agent homes for
Agent runtime config.

### Requirement: Credential references use flat environment examples

**Reason**: Connector credential examples are no longer documented through
`config/settings.yaml.example`; Platform and Agent examples live beside runtime files.

**Migration**: Put Platform env examples in root `.env.example` and Agent runtime credential
references in `agents/<agent-id>/.env.example` / `agent.yaml`.

### Requirement: Global config files are optional

**Reason**: This requirement described the intermediate `config/platform/` and `config/agent/`
template split, which has been replaced by root Platform home and `agents/<agent-id>/` Agent
homes.

**Migration**: Use `.env`, `platform.yaml`, `agents/<agent-id>/agent.yaml`, and
`agents/<agent-id>/.env`.
