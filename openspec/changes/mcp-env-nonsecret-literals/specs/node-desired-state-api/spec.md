## MODIFIED Requirements

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
