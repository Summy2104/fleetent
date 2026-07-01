## MODIFIED Requirements

### Requirement: KB to Agent binding matrix
The system SHALL persist KB↔Agent bindings in an `agent_kbs` table scoped by (tenant_id, kb_id, agent_id), and SHALL expose binding management from exactly two views: the KB detail view (`/admin/kb/{kb_id}/agents`) and the agent detail view (`/admin/agents/{name}/kbs`). No third reverse-lookup endpoint SHALL exist. The agent→KB reverse view SHALL exclude bindings whose KB is archived (callers see only live KBs for the agent). Bindings SHALL be admin-only to change and viewer-readable.

#### Scenario: Bind a KB to an agent
- **WHEN** an admin binds kb_id "support" to agent "support-bot"
- **THEN** the binding is persisted in `agent_kbs` and an audit entry (`kb_bind_agent`) is written

#### Scenario: View bindings from both sides
- **WHEN** an admin or viewer opens a KB's binding list or an agent's KB list
- **THEN** the consistent set of (kb_id, agent_id) bindings for the current tenant is shown

#### Scenario: 反查视图排除已归档 KB
- **WHEN** 从 agent 侧视图（`/admin/agents/{name}/kbs`）读取该 agent 绑定的 KB 列表，且其中某 KB 已归档
- **THEN** 返回列表排除已归档 KB（只列 live KB），与原 `by-agent` 端点行为一致

#### Scenario: 无第三反查端点
- **WHEN** 审视 KB / agent 管理 API 的路由
- **THEN** 不存在 `/admin/kb/by-agent/{agent_id}`（已退役）；agent→KB 反查唯一入口为 `/admin/agents/{name}/kbs`

#### Scenario: Unbind is audited
- **WHEN** an admin removes a KB↔Agent binding
- **THEN** the binding is deleted and an audit entry (`kb_unbind_agent`) is written

#### Scenario: Viewer cannot change bindings
- **WHEN** a viewer attempts to bind or unbind
- **THEN** the request returns 403
