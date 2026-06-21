## MODIFIED Requirements

### Requirement: 分区期望态拉取

系统 SHALL 暴露 `GET /nodes/{id}/desired-state`，返回该 node 应运行的 agent 集合及其下发配置。集合 SHALL 满足：

- **按 placement 分区**：只含 pin 到该 node 的 agent（C1 `placement_store.list_by_node`）。
- **按 status 过滤**：只含 `agent_admin_state.status == "enabled"` 的 agent；`disabled` / `archived` SHALL NOT 出现。这是 status **第一次真正生效**的接线点。
- **携带 materialized 配置**：每个 agent 附其下发用配置载荷（复用 `materialize.agent_file_from_store` 产出 agent.yaml 内容，**序列化进响应、不写本地盘**）。本 change 的配置载荷为**非密**部分；secret 由后续 change（`node-secret-delivery`）扩展。
- **保留非密指针、仅剥密钥值**：非密载荷 MUST 保留**非密的指针字段**——`*_env` 形态的字段(其值是 env 变量名，如 `api_key_env="ANTHROPIC_API_KEY"`)，使 node 写出的 `agent.yaml` 能携带 `api_key_env`、运行时 resolver 据此去 `.env` 解析模型 key。剥离 SHALL 只针对**承载密钥值**的内容——`env` 字典(`key == "env"`)与 `credential_ref`。载荷 MUST NOT 含任何明文密钥值。

#### Scenario: 只返回本 node 且 enabled 的 agent

- **WHEN** node 拉取期望态，其上 pin 了 agentA(enabled)、agentB(disabled)、agentC(archived)
- **THEN** 响应只含 agentA；agentB、agentC 不出现

#### Scenario: 每个 agent 附配置载荷

- **WHEN** 期望态返回 agentA
- **THEN** agentA 条目含其 materialized agent.yaml 内容（非密字段），node 据此可写本地 home

#### Scenario: 配置载荷保留 api_key_env 指针

- **WHEN** agentA 的 model target 配了 `api_key_env`（如 `ANTHROPIC_API_KEY`），期望态返回 agentA
- **THEN** 载荷中该 target **仍含 `api_key_env`** 字段，node 写出的 `agent.yaml` 带此指针，运行时可解析模型 key

#### Scenario: 配置载荷剥离密钥值

- **WHEN** agentA 的配置含承载密钥值的 `env` 字典或 `credential_ref`
- **THEN** 载荷中这些**密钥值被剥除**，desired-state 不含任何明文密钥；密钥值改由 secret 下发路径单独提供

#### Scenario: 空归属返回空集

- **WHEN** node 上没有任何 enabled 的 pin agent
- **THEN** 响应返回空 agent 集合（非错误）
