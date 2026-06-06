## MODIFIED Requirements

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

## ADDED Requirements

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
