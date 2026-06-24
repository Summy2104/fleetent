## MODIFIED Requirements

### Requirement: 各资源投影语义

approvals 投影 SHALL join 身份（agent 侧不透明 actor → 真实身份经 #4/management 解析）；user memory 投影 SHALL 跨该 user 谈过的 agent 遍历（内容投影可选）；**agent memory 投影 SHALL per-agent 直读该 agent 的 `agent_state.db`（`agent_memory_items` 表）**（不再读独立 `agent_memory.db`，不 per-tenant 聚合、不跨 agent 遍历）。投影 SHALL 走只读、不迁移的 open。

#### Scenario: approvals 投影解析身份

- **WHEN** platform 投影审批历史
- **THEN** 读 agent 侧 approval_store（只读）+ join 身份解析出"谁批的"（#4 落地后）

#### Scenario: agent memory per-agent 直读 agent_state.db

- **WHEN** platform 投影某 agent 的 agent memory
- **THEN** 只读该 agent 的 `agent_state.db` 的 `agent_memory_items`（经 per-agent 只读句柄），不读独立 `agent_memory.db`、不 per-tenant 聚合、不遍历其它 agent
