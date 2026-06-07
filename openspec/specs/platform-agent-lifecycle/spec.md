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

### Requirement: Agent materialization exports the full authored definition

平台 materialize（DB→file）SHALL 从已存的 agent 定义生成**可真实部署**的 `agent.yaml`，回填平台
已存的全部字段，而非只导出核心几项后将其余落到 schema 默认。`models` SHALL 由 agent 的 model
选择/覆盖展开，而非无条件使用本地 `default_models()` 占位。

#### Scenario: 已存核心字段回填
- **WHEN** 一个含 `tenant_id` / `team_id` / `skills_dir` 的 agent 被 materialize
- **THEN** 生成的 `agent.yaml` 含这三个字段的真实值

#### Scenario: model 覆盖展开为真实 targets/routes
- **WHEN** 一个 agent 选定了一个或多个 provider
- **THEN** `models.targets[*]` 由所选 provider 展开
- **AND** 每个 target 的 `api_key_env` 复用对应 provider 的 `api_key_env`
- **AND** 不出现 `localhost` 占位模型

#### Scenario: 无 model 覆盖时回退默认
- **WHEN** 一个 agent 没有任何 model 选择/覆盖
- **THEN** `models` 回退到 `default_models()`

#### Scenario: MCP / bindings / knowledge 接入导出
- **WHEN** 一个 agent 绑定了 MCP server、channel/user、KB
- **THEN** 生成的 `agent.yaml` 分别含 `mcp_servers`、`bindings.channels`/`bindings.users`、`knowledge.bindings`

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

### Requirement: Process-level env template separated from agent secrets

部署 env 模板 SHALL 拆分：`config/agent/.env.example` 只保留 `agent.yaml` 中 `*_env` 引用不到的
进程级变量（含新增的 `FLEETENT_SECRET_KEY`、`DATABASE_URL`、`MICROSANDBOX_URL`、运行调优等）。
agent 引用的密钥占位 SHALL NOT 出现在该模板中——它们由 materialize 生成并经 console 面板提供。

#### Scenario: 进程级模板含 secret key
- **WHEN** 读取 `config/agent/.env.example`
- **THEN** 含 `FLEETENT_SECRET_KEY`

#### Scenario: agent 密钥不在进程级模板
- **WHEN** 读取 `config/agent/.env.example`
- **THEN** 不含 model / Slack / MCP / KB 的 agent 级 `*_env` 占位

#### Scenario: 模板无 inline 密钥值
- **WHEN** 读取 `config/agent/.env.example`
- **THEN** 所有条目为 `NAME=` 形式，不含任何真实密钥值
