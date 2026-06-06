# platform-agent-lifecycle Specification

## Purpose
Platform-side agent lifecycle: creating/updating an agent materializes its runnable
self-contained home, and the platform can start/stop the agent as a `fleetent agent run`
process without monitoring it. Created by archiving change platform-agent-lifecycle.
## Requirements
### Requirement: Create/update materializes a runnable agent home

When the platform creates or updates an agent, it SHALL materialize that agent's
self-contained home: an `agent.yaml` (definition + `connectors` + per-agent `access`
block) and a `.env` scaffold (env-var names only, no plaintext secrets), under the
agent's home directory, so the agent is runnable by `fleetent agent run`.

#### Scenario: Create writes the home

- **WHEN** an admin creates agent `support` on the platform
- **THEN** `FLEETENT_HOME/support/agent.yaml` is written from the authored definition and
  a `.env` scaffold is present, with secrets referenced only by env-var name

#### Scenario: Update re-materializes

- **WHEN** an admin edits `support`'s definition
- **THEN** its home `agent.yaml` is rewritten to match, leaving operator-provided `.env`
  secret values intact

### Requirement: Start and stop agent processes without monitoring

The platform SHALL be able to start an agent by spawning `fleetent agent run <name>` as a
subprocess and to stop it by terminating the tracked process. The platform SHALL track
started PIDs to stop them, and SHALL NOT health-monitor, auto-restart, or supervise the
agent processes.

#### Scenario: Start spawns the agent runtime

- **WHEN** `POST /admin/agents/support/start` is called
- **THEN** the platform spawns `fleetent agent run support` (materializing the home first
  if needed) and records the process

#### Scenario: Stop terminates the tracked process

- **WHEN** `POST /admin/agents/support/stop` is called for a started agent
- **THEN** the platform terminates that tracked process

#### Scenario: No supervision

- **WHEN** a started agent process exits on its own
- **THEN** the platform does not restart it and reports it as not-running; recovery
  requires an explicit start

### Requirement: Agent materialization writes self-contained Agent homes

平台 materialize SHALL 将每个 Agent 写成 self-contained Agent home under
`agents/<agent-id>/`. 该 home SHALL 包含 `agent.yaml`, `.env`, and `data/`; runtime SHALL be
able to run from that home without Platform DB access. Platform-owned config files such as
`platform.yaml` and embedded Knowledge construction files SHALL NOT be written into Agent homes.

#### Scenario: Materialize writes Agent home
- **WHEN** 平台部署 Agent `support`
- **THEN** materialize 写入 `agents/support/agent.yaml`
- **AND** 写入或保留 `agents/support/.env`
- **AND** 确保 `agents/support/data/` 存在

#### Scenario: Platform env does not leak into Agent home
- **WHEN** materialize 写入 Agent `.env`
- **THEN** `.env` 只含该 Agent required env
- **AND** 不含 `FLEETENT_SECRET_KEY`、`DATABASE_URL` 或 Platform-owned KB construction env

#### Scenario: Knowledge binding export only
- **WHEN** 一个 agent 绑定了 KB
- **THEN** 生成的 `agent.yaml` 含 `knowledge.bindings`
- **AND** 不含 Google Drive / Confluence source construction details
- **AND** materialize 不写 `config/knowledge.yaml`

### Requirement: `.env` materialization resolves by credential mode

`.env` 生成 SHALL 按每个密钥槽的 mode 决定值的来源：`inject` 槽 SHALL 写入解密后的真实值；
`operator` 槽 SHALL 只写 `NAME=` 占位并保留运维已填的现有值。生成的 `agent.yaml` SHALL 与 mode
无关，始终只含 `*_env` 引用。

#### Scenario: inject 槽写真实值
- **WHEN** 一个 inject 槽已设值且 materialize 运行
- **THEN** `.env` 中该 env 名被赋为解密后的值

#### Scenario: operator 槽留空并保留运维值
- **WHEN** 一个 operator 槽被 materialize
- **THEN** 若 `.env` 已有该 env 名的运维值则原样保留
- **AND** 否则写入空占位 `NAME=`

#### Scenario: inject 已标记但解密失败时 fail loud
- **WHEN** 一个 inject 槽状态为 set 但解密失败
- **THEN** materialize fail loud
- **AND** 不静默写空值

#### Scenario: agent.yaml 不含密钥值
- **WHEN** 任意 mode 组合下 materialize 运行
- **THEN** 生成的 `agent.yaml` 不含任何密钥明文

### Requirement: Platform env template separated from Agent env materialization

部署 env SHALL 按 Platform / Agent 边界拆分：`FLEETENT_SECRET_KEY`、`DATABASE_URL`、
`MICROSANDBOX_URL`、`LOG_FORMAT` 等平台进程变量 SHALL 属于 Platform ENV 模板；Agent `.env`
SHALL 由 materialize 写入对应 Agent home，只包含该 Agent 运行所需的 `*_env` 值或空占位。
agent 引用的密钥占位 SHALL NOT 出现在 Platform ENV 模板中——它们由 materialize 生成并经 console
面板提供。

#### Scenario: Platform env 模板含 secret key
- **WHEN** 读取 Platform ENV 模板
- **THEN** 含 `FLEETENT_SECRET_KEY`

#### Scenario: agent 密钥不在 Platform env 模板
- **WHEN** 读取 Platform ENV 模板
- **THEN** 不含 model / Slack / MCP / KB 的 agent 级 `*_env` 占位

#### Scenario: Agent env 由 materialize 产生
- **WHEN** materialize 一个含 operator 与 inject 槽的 Agent
- **THEN** `<agent-home>/.env` 含该 Agent 所需 env 名
- **AND** 不含 `FLEETENT_SECRET_KEY` 或平台进程变量

#### Scenario: 模板无 inline 密钥值
- **WHEN** 读取 Platform ENV 模板
- **THEN** 所有条目为 `NAME=` 形式，不含任何真实密钥值

