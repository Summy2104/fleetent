## MODIFIED Requirements

### Requirement: agents.id 是不可变身份、agents.name 是可变可读标签
`agents.id`（INTEGER 代理键）SHALL 是 agent 的不可变身份与平台所有关系表的 FK 键，永不暴露给人 / 物理层；`agents.name`（slug）SHALL 是**可变**的人类可读标签，仅存于 `agents` 表一列 + agent 侧产物（物理目录 `agents/<name>/`、agent.yaml、`traces.agent_name`）+ 显示层。关系完整性只挂 `agents.id`，故 name 变更**零关系级联**（依据 `docs/architecture/agent-identity-model.md`）。

平台侧对 agent 的**关系写/查 SHALL 以 `agents.id`(INTEGER) 为键**：除按 name 做一次性查找解析（如 `get_by_name` / 人面 URL 的 `_require_agent(name)`）外，平台 store 的 agent 变更/绑定/查询函数 SHALL NOT 以 `name` 作为参数键或 SQL WHERE 键（先解析成 `agents.id` 再操作）。

当前系统**不提供改名 API**（store / admin / console 均无修改 `agents.name` 的写路径，YAGNI）。若未来加入，rename SHALL = 改 `agents.name` 一行 + 在写边界 re-materialize 重刷 agent 侧产物（物理目录搬迁 / agent.yaml 重写；`traces` 历史行保留旧 name），**不触碰任何平台关系键**。

#### Scenario: 平台关系键挂 id 不挂 name
- **WHEN** 审视平台侧引用 agent 的表（`agent_admin_state` / `session_meta` / 各绑定表等）
- **THEN** agent 引用一律为 `agent_id` INTEGER FK→`agents.id`；除 `agents.name` 列本身外，不存在以 name 引用 agent 的列

#### Scenario: 平台 store 变更函数按 id 键不按 name 键
- **WHEN** 审视平台 `agent_store` 及各绑定 store 的 agent 变更/绑定/查询函数（如 set_im_capabilities、assign_user、bind_mcp_server 等）
- **THEN** 其 agent 参数与 SQL WHERE 键均为 `agent_id`(INTEGER)；除 name→id 的一次性查找解析（get_by_name / _require_agent）外，不存在以 name 直接寻址 agent 的变更/查询路径

#### Scenario: 当前无 rename 写路径
- **WHEN** 检查 `agent_store`、`agent_admin_store` 与 agent console API
- **THEN** 不存在修改 `agents.name` 的函数或端点（rename 暂未提供；如启用，按上述写边界 re-materialize 语义实现）

### Requirement: Runtime agent resolution is file-sourced

At runtime the system SHALL resolve an agent's executable `AgentSnapshot` from its
self-contained file `agents/<name>/agent.yaml`, not from the
`agents`/`agent_versions` SQLite read path. The snapshot's runtime fields
(`system_prompt`, `allowed_tools`, `skills_dir`, `model_overrides`, `memory_namespace`)
SHALL come from the file, and the agent's runtime identity SHALL be its `name`. The DB
authoring requirements (creating `agents`/`agent_versions` rows via the admin console
and CLI) are unchanged; the file is the runtime artifact generated from them.

agent 侧进程内承载 agent 身份的运行时载体（如 `AgentSnapshot`、命令上下文、模型策略快照等）承载的值 SHALL 为 agent `name`（与文件产物一致，非平台 `agents.id`——standalone/file agent 无 int id 且解耦契约禁止依赖 management.db）；此类载体的身份字段命名 SHALL 反映其承载 name（如 `agent_name`），SHALL NOT 命名为 `agent_id` 以免与平台 INTEGER 身份混淆。

#### Scenario: Active snapshot resolved from file, not DB

- **WHEN** a message is routed to agent `assistant` and `agents/assistant/agent.yaml` exists
- **THEN** the applied `AgentSnapshot` (system_prompt, allowed_tools, skills_dir,
  model_overrides, memory_namespace) is read from that file and identified by the name
  `assistant`, with no `agents`/`agent_versions` read

#### Scenario: Missing agent file resolves to nothing

- **WHEN** routing references agent name `ghost` but no `agents/ghost/agent.yaml` exists
- **THEN** runtime resolution returns no snapshot and the request proceeds as a bare run

#### Scenario: 运行时载体身份字段承载 name 且命名一致
- **WHEN** 审视 agent 侧进程内运行时载体（`AgentSnapshot` / 命令上下文 / 模型策略快照）的 agent 身份字段
- **THEN** 该字段承载 agent `name`、命名反映其为 name（不叫 `agent_id`），与文件产物及 `traces.agent_name` 一致
