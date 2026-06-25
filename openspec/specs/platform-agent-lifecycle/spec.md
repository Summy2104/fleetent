# platform-agent-lifecycle Specification

## Purpose
Platform-side agent lifecycle: creating/updating an agent materializes its runnable
self-contained home, and the platform can start/stop the agent as a `fleetent agent run`
process without monitoring it. Created by archiving change platform-agent-lifecycle.
## Requirements
### Requirement: Create/update materializes a runnable agent home

When the platform creates or updates a managed agent, it SHALL update the management database and make a new desired-state payload available to the owning node. Platform SHALL NOT write the managed agent's real home directly. The owning node SHALL materialize the runnable home under `FLEETENT_HOME/tenants/<tenant>/agents/<agent>/`.

#### Scenario: Create exposes desired state
- **WHEN** an admin creates managed agent `support` on the platform
- **THEN** platform persists the authored definition in management DB
- **AND** `GET /nodes/{node-id}/desired-state` includes `support` for its placement
- **AND** platform does not write `tenants/<tenant>/agents/support/agent.yaml` itself

#### Scenario: Update changes desired state
- **WHEN** an admin edits `support`'s definition
- **THEN** platform updates the management DB source of truth
- **AND** the next desired-state response contains the updated agent config
- **AND** the owning node is responsible for rewriting the home and restarting if needed

### Requirement: Agent materialization writes self-contained Agent homes

Managed Agent homes SHALL be self-contained under `tenants/<tenant>/agents/<agent>/`, but in managed mode the writer SHALL be node reconcile. Platform-owned config files such as `platform.yaml` and embedded Knowledge construction files SHALL NOT be written into Agent homes.

#### Scenario: Node materializes Agent home
- **WHEN** node reconciles desired agent `support` in tenant `acme`
- **THEN** node writes `tenants/acme/agents/support/agent.yaml`
- **AND** writes or preserves `tenants/acme/agents/support/.env`
- **AND** ensures `tenants/acme/agents/support/data/` exists

#### Scenario: Platform managed path does not write home
- **WHEN** platform creates, updates, clones, or applies a managed agent definition
- **THEN** platform does not write `agent.yaml`, `.env`, `skills/`, or `data/` under that agent's home

#### Scenario: Knowledge binding export only
- **WHEN** 一个 agent 绑定了 KB
- **THEN** desired-state 中的 agent config 含 `knowledge.bindings`
- **AND** 不含 Google Drive / Confluence source construction details
- **AND** platform 不写 standalone Knowledge YAML 到 agent home

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
`LOG_FORMAT` 等平台进程变量 SHALL 属于 Platform ENV 模板（`.env.example`）；Agent `.env`
SHALL 由 materialize 写入对应 Agent home，只包含该 Agent 运行所需的 `*_env` 值或空占位。
agent 引用的密钥占位 SHALL NOT 出现在 Platform ENV 模板中——它们由 materialize 生成并经 console
面板提供。

`MICROSANDBOX_URL` 已从当前代码中移除（无任何代码读取此 env var）；Platform ENV 模板
SHALL NOT 再包含此变量。`FLEETENT_AUTO_UPGRADE` 同样为死变量，SHALL NOT 出现在模板中。

`PERMISSION_GATE_*` 和 `CONTEXT_*` 系列变量是 `AgentFile` 的 agent.yaml 字段，不是 env var，
SHALL NOT 出现在任何 `.env.example` 模板中。

#### Scenario: Platform env 模板含 secret key

- **WHEN** 读取 Platform ENV 模板（`.env.example`）
- **THEN** 含 `FLEETENT_SECRET_KEY=`

#### Scenario: agent 密钥不在 Platform env 模板

- **WHEN** 读取 Platform ENV 模板
- **THEN** 不含 model / Slack / MCP / KB 的 agent 级 `*_env` 占位

#### Scenario: 死变量不在 Platform env 模板

- **WHEN** 读取 Platform ENV 模板
- **THEN** 不含 `MICROSANDBOX_URL`
- **AND** 不含 `FLEETENT_AUTO_UPGRADE`
- **AND** 不含 `PERMISSION_GATE_MEDIUM_TIMEOUT_SECONDS`
- **AND** 不含 `CONTEXT_MAX_TOKENS`

#### Scenario: Agent env 由 materialize 产生

- **WHEN** materialize 一个含 operator 与 inject 槽的 Agent
- **THEN** `<agent-home>/.env` 含该 Agent 所需 env 名
- **AND** 不含 `FLEETENT_SECRET_KEY` 或平台进程变量

#### Scenario: 模板无 inline 密钥值

- **WHEN** 读取 Platform ENV 模板
- **THEN** 所有条目为 `NAME=` 形式，不含任何真实密钥值

---

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

平台 SHALL NOT 直接将 skill 文件分发到 managed agent home。平台 SHALL 在 desired-state 中提供 skill manifest 与 bundle URL；node SHALL 下载 bundle 并部署到 agent home 的 `skills/` 目录。standalone/local helper MAY copy skills locally, but it is not the managed production path.

#### Scenario: Platform desired state references skill bundles
- **WHEN** agent `support` 启用 skill `foo`
- **THEN** desired-state 包含 `foo` 的 `base_version`、`base_commit`、`bundle_url` 与 `bundle_sha256`
- **AND** platform 不 copy `foo` 到 managed agent home

#### Scenario: Node deploys skill files
- **WHEN** node reconcile 看到本地缺少 desired skill `foo` 的 `base_version`
- **THEN** node 下载 bundle
- **AND** 解压部署到 `tenants/<tenant>/agents/<agent>/skills/foo/`

### Requirement: collect_env_var_names 覆盖 MCP stdio env: 引用

`collect_env_var_names` SHALL 除收集所有 `*_env` 字段外，还收集 MCP server **`env:` dict
和 `headers:` dict** 中以 `"env:"` 前缀开头的值所引用的变量名（截取前缀后的部分）。结果
SHALL 与 `*_env` 收集结果合并去重、排序后返回。

此行为与 `mcp/client.py` 的 `_resolve_env_ref` 逻辑一致——该解析器同时作用于 stdio
`env:` 值（`_subprocess_env`）和 http `headers:` 值（`_http_headers`），两处的 `env:`
引用都 SHALL 被收集，确保 MCP 服务的环境变量引用在 agent `.env` scaffold 中有对应占位。

#### Scenario: MCP env:VAR 引用被收集（stdio env）

- **WHEN** agent.yaml 中某 MCP server 配置 `env: {DB_URL: "env:MY_DATABASE_URL"}`
- **THEN** `collect_env_var_names` 返回值包含 `MY_DATABASE_URL`

#### Scenario: MCP headers 中的 env:VAR 引用被收集（http headers）

- **WHEN** agent.yaml 中某 MCP server 配置 `headers: {Authorization: "env:MY_TOKEN"}`
- **THEN** `collect_env_var_names` 返回值包含 `MY_TOKEN`

#### Scenario: MCP env 纯值不被误收集

- **WHEN** agent.yaml 中某 MCP server 配置 `env: {MODE: "production"}`（无 `env:` 前缀）
- **THEN** `collect_env_var_names` 返回值不包含 `MODE` 或 `production`

#### Scenario: 与 *_env 字段合并去重

- **WHEN** agent 同时有 `api_key_env: FOO` 字段和 MCP `env: {K: "env:FOO"}`
- **THEN** `collect_env_var_names` 返回值中 `FOO` 只出现一次

