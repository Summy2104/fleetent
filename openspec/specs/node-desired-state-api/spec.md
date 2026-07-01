# node-desired-state-api Specification

## Purpose
TBD - created by archiving change node-desired-state-api. Update Purpose after archive.
## Requirements
### Requirement: node 鉴权

系统 SHALL 用 node service key（C1 `nodes.key_hash`）鉴权 node 的所有期望态/上报请求。请求 SHALL 携带 `Authorization: Bearer ma-<hex>`，经 `node_store.resolve_node_key` 解析为 node 身份；解析失败 SHALL 拒绝（401）。一个 node SHALL 只能访问/上报**自己**（URL 中的 `{id}` 必须等于其 key 解析出的 node-id），跨 node 访问 SHALL 拒绝（403）。

#### Scenario: 有效 node key 通过且仅限自身

- **WHEN** node 以其 service key 请求 `/nodes/{自身id}/...`
- **THEN** 系统接受并在该 node 作用域内执行

#### Scenario: 无效 key 拒绝

- **WHEN** 请求携带缺失或不匹配 `nodes.key_hash` 的 key
- **THEN** 系统返回 401，不进入业务逻辑

#### Scenario: 跨 node 访问拒绝

- **WHEN** node A 的 key 请求 `/nodes/{B 的 id}/...`
- **THEN** 系统返回 403

### Requirement: 分区期望态拉取

系统 SHALL 暴露 `GET /nodes/{id}/desired-state`，返回该 node 应运行的 agent 集合及其下发配置。集合 SHALL 满足：

- **按 placement 分区**：只含 pin 到该 node 的 agent（C1 `placement_store.list_by_node`）。
- **按 status 过滤**：只含 `agent_admin_state.status == "enabled"` 的 agent；`disabled` / `archived` SHALL NOT 出现。
- **携带 materialized 配置**：每个 agent 附其下发用配置载荷（复用 `materialize.agent_file_from_store` 产出 agent.yaml 内容，**序列化进响应、不写本地盘**）。
- **保留非密指针字段**：`*_env` 形态字段（值是 env 变量名，如 `api_key_env="ANTHROPIC_API_KEY"`）SHALL 被保留下发。
- **MCP `env` 字典的下发口径（写法即密/非密声明）**：MCP server `env` 字典内——
  - **`env:VAR` 形态的值**是指向 `.env` 变量名的 **secret 指针**（语义同 `*_env`），SHALL 被保留下发；node 重算 `referenced_env_names` 时收集到 `VAR`，在 `.env` scaffold 并由 secret 通道填值，运行时经 `env:` 解析注入 stdio 子进程。
  - **其余字符串明文值**是 **operator 显式声明的非密配置**（如 @aashari Atlassian MCP 的 `ATLASSIAN_USER_EMAIL` / `ATLASSIAN_SITE_NAME`），SHALL 被原样保留下发；node 据此写出 `agent.yaml`，运行时整值透传给 stdio 子进程。
- **仍剥离密钥值字段**：`credential_ref` SHALL 被剥除，不入载荷；经 secret 通道（`env:VAR` + secret 存储）管理的密钥**值**亦不进载荷。真 secret SHALL 经 `env:VAR` 表达——operator 对 MCP `env` 内明文值的非密性负责（不得内联真 secret）。

#### Scenario: 只返回本 node 且 enabled 的 agent

- **WHEN** node 拉取期望态，其上 pin 了 agentA(enabled)、agentB(disabled)、agentC(archived)
- **THEN** 响应只含 agentA；agentB、agentC 不出现

#### Scenario: 配置载荷保留 api_key_env 指针

- **WHEN** agentA 的 model target 配了 `api_key_env`（如 `ANTHROPIC_API_KEY`），期望态返回 agentA
- **THEN** 载荷中该 target **仍含 `api_key_env`** 字段，node 写出的 `agent.yaml` 带此指针，运行时可解析模型 key

#### Scenario: MCP env 的 env: 引用作为 secret 指针被保留

- **WHEN** agentA 绑定的 MCP server 的 `env` 字典含 `env:VAR` 引用（如 `{"JIRA_API_TOKEN": "env:JIRA_API_TOKEN"}`），期望态返回 agentA
- **THEN** 载荷中该 server 的 `mcpServers.<id>.env` **仍含该 `env:VAR` 引用**；node 据此 scaffold/填值后经运行时 `env:` 解析注入 stdio 子进程

#### Scenario: MCP env 的明文值作为非密配置被保留

- **WHEN** agentA 绑定的 MCP server 的 `env` 字典含明文值（非 `env:` 引用，如 `{"ATLASSIAN_USER_EMAIL": "r.intern.dev@example.test", "ATLASSIAN_SITE_NAME": "antalpha"}`），期望态返回 agentA
- **THEN** 载荷中该 server 的 `mcpServers.<id>.env` **仍含这些明文键值**；node 写出的 `agent.yaml` 携带它们，运行时整值透传给 stdio 子进程（使其完成 Basic auth）

#### Scenario: 配置载荷仍剥离 credential_ref

- **WHEN** agentA 的配置含 `credential_ref`（专用 secret-值字段）
- **THEN** 载荷中 `credential_ref` 被剥除，不进 desired-state；密钥值改由 secret 下发路径单独提供

#### Scenario: 空归属返回空集

- **WHEN** node 上没有任何 enabled 的 pin agent
- **THEN** 响应返回空 agent 集合（非错误）

### Requirement: 实际态上报与心跳

系统 SHALL 暴露 `POST /nodes/{id}/status`，接收 node 上报的**实际态**（其上各 agent 是否在跑 / PID / 健康）与心跳。上报 SHALL 更新该 node 的 `nodes.last_seen_at`（C1 已建该列），并 SHALL 持久化 per-agent 实际态供控制台/可观测读取。实际态是**只读投影**（控制真相在 node 的 PID 文件），platform 不据其做控制决策。

#### Scenario: 心跳刷新 last_seen_at

- **WHEN** node POST 上报
- **THEN** 系统将该 node 的 `last_seen_at` 更新为当前时间

#### Scenario: per-agent 实际态可被查询

- **WHEN** node 上报 agentA running(pid=123) 后，控制台查询该 node 实际态
- **THEN** 返回 agentA running/pid 等已上报字段

#### Scenario: 上报受 node 鉴权与自限约束

- **WHEN** 上报请求的 key 无效或 `{id}` 非自身
- **THEN** 分别按 401 / 403 拒绝（同 node 鉴权要求）

### Requirement: Desired-state includes tenant-aware home inputs

`GET /nodes/{node-id}/desired-state` SHALL include enough information for node to resolve each managed agent's tenant-aware home, including platform `agent_id`, stable `name`, `tenant_id`, non-secret agent config, and secrets/env values partitioned for that agent.

#### Scenario: Desired agent carries tenant id
- **WHEN** platform returns desired-state for node `local-node`
- **THEN** each agent entry includes `tenant_id`
- **AND** node can derive `tenants/<tenant_id>/agents/<name>/` without querying management DB directly

### Requirement: Desired-state includes skill manifests

desired-state SHALL include a skill manifest for each skill that node must deploy for the agent. The manifest SHALL include `name`, `base_version`, `base_commit`, `bundle_url`, and `bundle_sha256`; it SHALL NOT inline arbitrary file contents.

#### Scenario: Enabled skill appears as manifest entry
- **WHEN** agent `support` has enabled skill `foo`
- **THEN** desired-state for `support` includes a manifest entry for `foo`
- **AND** the entry contains version and bundle verification metadata

#### Scenario: Disabled skill does not require bundle deployment
- **WHEN** a globally disabled skill is present in the public pool
- **THEN** desired-state may include it in `disabled_skills` for agent.yaml
- **AND** node is not required to deploy its bundle for runtime use

### Requirement: Desired-state cache strips secret and bundle payload contents

node's desired-state cache SHALL NOT store plaintext secret values beyond the `.env` scaffold responsibility, and SHALL NOT cache full skill bundle file contents inside `desired-state-cache.json`. It MAY cache skill manifest metadata.

#### Scenario: Cache contains manifest not bundle contents
- **WHEN** node caches desired-state locally
- **THEN** cache contains skill names and version metadata
- **AND** cache does not contain `SKILL.md` contents or packed bundle bytes

