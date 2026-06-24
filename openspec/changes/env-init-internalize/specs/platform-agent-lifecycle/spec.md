## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: collect_env_var_names 覆盖 MCP stdio env: 引用

`collect_env_var_names` SHALL 除收集所有 `*_env` 字段外，还收集 MCP server `env:` dict 中
以 `"env:"` 前缀开头的值所引用的变量名（截取前缀后的部分）。结果 SHALL 与 `*_env` 收集结果
合并去重、排序后返回。

此行为与 `mcp/client.py` 的 `_resolve_env_ref` 逻辑一致，确保 MCP stdio 服务的环境变量
引用在 agent `.env` scaffold 中有对应占位。

#### Scenario: MCP env:VAR 引用被收集

- **WHEN** agent.yaml 中某 MCP server 配置 `env: {DB_URL: "env:MY_DATABASE_URL"}`
- **THEN** `collect_env_var_names` 返回值包含 `MY_DATABASE_URL`

#### Scenario: MCP env 纯值不被误收集

- **WHEN** agent.yaml 中某 MCP server 配置 `env: {MODE: "production"}`（无 `env:` 前缀）
- **THEN** `collect_env_var_names` 返回值不包含 `MODE` 或 `production`

#### Scenario: 与 *_env 字段合并去重

- **WHEN** agent 同时有 `api_key_env: FOO` 字段和 MCP `env: {K: "env:FOO"}`
- **THEN** `collect_env_var_names` 返回值中 `FOO` 只出现一次
