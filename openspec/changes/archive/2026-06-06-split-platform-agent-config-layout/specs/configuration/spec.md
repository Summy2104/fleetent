## ADDED Requirements

### Requirement: Configuration is split by Platform and Agent perspective

配置 SHALL 按 Platform side 与 Agent side 两个视角组织，而不是按历史模板路径或内部模块名混放。
Platform side SHALL own 平台进程配置、平台 env、平台 DB、Agent authoring/deployment/materialize，以及默认
内嵌的 knowledge / memory / worker 能力。Agent side SHALL own 某个 Agent runtime 的 `agent.yaml`、
`.env` 与 `data/`。

#### Scenario: Platform config is the authoring source
- **WHEN** 平台部署一个 Agent
- **THEN** 平台从 Platform DB + Platform config/env 派生该 Agent 的 runtime home
- **AND** Agent runtime 不读取 Platform DB 或 Platform config

#### Scenario: Agent home is self-contained
- **WHEN** 查看一个已 materialize 的 Agent home
- **THEN** 它包含 `agent.yaml`、`.env` 和 `data/`
- **AND** `agent.yaml` 只含非敏感配置与 env 引用
- **AND** `.env` 只含该 Agent runtime 所需变量

### Requirement: Platform env and Agent env are separate

The system SHALL keep Platform process environment variables separate from Agent runtime
environment variables.

`FLEETENT_SECRET_KEY`、`DATABASE_URL`、平台日志、sandbox endpoint、未来 remote service endpoint 等平台
进程变量 SHALL 属于 Platform ENV。model provider key、IM token、MCP secret、KB connector secret 等
Agent runtime 变量 SHALL 属于 Agent ENV。

#### Scenario: Platform secret key is not an Agent env
- **WHEN** 平台 materialize 一个 Agent home
- **THEN** `<agent-home>/.env` 不含 `FLEETENT_SECRET_KEY`
- **AND** `FLEETENT_SECRET_KEY` 只出现在 Platform ENV 模板/部署环境中

#### Scenario: Agent required env is materialized
- **WHEN** 一个 Agent 引用 model / MCP / connector / KB secret env
- **THEN** materialize 在 `<agent-home>/.env` 中写入对应 env 名和值或空占位

### Requirement: Canonical templates avoid ambiguous agent paths

仓库 canonical 模板 SHALL 清楚区分 Platform 与 Agent 模板。`config/agents/*` SHALL NOT be treated as
the canonical deployment template path; it MAY remain as dev/test examples for multi-agent scan.
Tracked concrete local files such as `config/agent.yaml` SHALL NOT be presented as canonical templates.

#### Scenario: Canonical templates are discoverable
- **WHEN** 查看仓库配置模板
- **THEN** 能区分 Platform YAML/ENV 模板与 Agent YAML/ENV 模板
- **AND** 不需要通过 `agent` / `agents` 单复数差异理解部署语义

#### Scenario: Multi-agent scan examples are not deployment templates
- **WHEN** 文档描述部署模板
- **THEN** 不把 `config/agents/<name>/agent.yaml.example` 描述为默认部署模板
