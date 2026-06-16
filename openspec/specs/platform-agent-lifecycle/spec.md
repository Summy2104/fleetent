# platform-agent-lifecycle Specification

## Purpose
Platform-side agent lifecycle: creating/updating an agent materializes its runnable
self-contained home, and the platform can start/stop the agent as a `fleetent agent run`
process without monitoring it. Created by archiving change platform-agent-lifecycle.
## Requirements
### Requirement: Create/update materializes a runnable agent home

When the platform creates or updates an agent, it SHALL materialize that agent's
self-contained home under `FLEETENT_HOME/agents/<agent-id>/`: an `agent.yaml`
(definition + `connectors` + per-agent `access` block), a `.env` scaffold, and `data/`,
so the agent is runnable by `fleetent agent run`.

#### Scenario: Create writes the home
- **WHEN** an admin creates agent `support` on the platform
- **THEN** `FLEETENT_HOME/agents/support/agent.yaml` is written from the authored definition
- **AND** `FLEETENT_HOME/agents/support/.env` is present, with secrets referenced only by env-var name
- **AND** `FLEETENT_HOME/agents/support/data/` exists

#### Scenario: Update re-materializes
- **WHEN** an admin edits `support`'s definition
- **THEN** `FLEETENT_HOME/agents/support/agent.yaml` is rewritten to match
- **AND** operator-provided `.env` secret values are preserved

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

#### Scenario: Old flat deploy path is not written
- **WHEN** 平台部署 Agent `support`
- **THEN** 不写入 `support/agent.yaml`
- **AND** 不写入 Platform home root `agent.yaml`

#### Scenario: Knowledge binding export only
- **WHEN** 一个 agent 绑定了 KB
- **THEN** 生成的 `agent.yaml` 含 `knowledge.bindings`
- **AND** 不含 Google Drive / Confluence source construction details
- **AND** materialize 不写 standalone Knowledge YAML

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

### Requirement: Materialize 将全局 disabled skills 写入 agent.yaml 的 disabled_skills

由于 agent 运行时只读 `agent.yaml`、从不访问 platform DB，平台的全局 skill disable 决策（`skill_admin_state.global_enabled=0`）SHALL 在 materialize 时被写入 `AgentFile.disabled_skills`。`agent_file_from_store()` SHALL 读取 `skill_admin_store.list_states()`，把所有 `global_enabled=0` 的 `skill_name` 汇集到 `disabled_skills`。

当 `skill_admin_state` 表不存在（旧库）时，materialize SHALL 安全回退到空 `disabled_skills`，不抛异常。

#### Scenario: 全局 disabled skill 写入 disabled_skills

- **WHEN** skill "crm-ops" 在 `skill_admin_state` 中 `global_enabled=0`，对任一 agent 触发 materialize
- **THEN** 产出的 agent.yaml 中 `disabled_skills` 包含 "crm-ops"

#### Scenario: 全局 enabled skill 不出现在 disabled_skills

- **WHEN** skill "jira" 在 `skill_admin_state` 中 `global_enabled=1`，触发 materialize
- **THEN** 产出的 agent.yaml 中 `disabled_skills` 不包含 "jira"

#### Scenario: 表缺失时安全回退

- **WHEN** `skill_admin_state` 表不存在，触发 materialize
- **THEN** materialize 正常完成，`disabled_skills` 为空列表，不抛异常

### Requirement: Materialize 将平台 skill 文件分发到 agent home

为使 agent home 自包含（agent 进程只读自己的 home），`write_home()` SHALL 在写出 `agent.yaml` 与 `data/` 后，把平台全局 skills 目录（`skill_registry._resolve_skills_dir(None)`）下的全部 skill 目录复制到 `<home>/skills/`。

- 复制 SHALL 是幂等的（重复 materialize 覆盖同名文件，不报错）
- 当全局 skills 目录不存在时，复制 SHALL 被跳过，不抛异常
- 复制失败（IO 错误）SHALL 记录结构化告警但不阻断 materialize（agent.yaml 已写出）
- 全量复制：所有 skill 进入 home，运行时可见性由 agent.yaml 的 `allowed_skills` / `disabled_skills` 决定（文件分发与可见性解耦）

#### Scenario: skill 文件复制到 agent home

- **WHEN** 全局 skills 目录含 `crm-ops/SKILL.md`，对 agent "support" 触发 materialize
- **THEN** `<support-home>/skills/crm-ops/SKILL.md` 存在且内容与源一致

#### Scenario: 源目录缺失时安全跳过

- **WHEN** 全局 skills 目录不存在，触发 materialize
- **THEN** materialize 正常完成，`<home>/skills/` 不被创建（或为空），不抛异常

#### Scenario: 重复 materialize 幂等

- **WHEN** 对同一 agent 连续两次 materialize
- **THEN** 第二次覆盖 `<home>/skills/` 中的同名文件，不因目录已存在而报错

