# kb-agent-binding Specification

## Purpose
TBD - created by archiving change 2026-06-02-knowledge-base-management. Update Purpose after archive.
## Requirements
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

### Requirement: Binding relation backs scope limiting and delete protection
The `agent_kbs` binding relation SHALL serve as the authoritative source for long-term-ctx to limit recall to the agent's bound kb_ids, and SHALL back KB archive/delete binding protection. The management plane maintains the bindings only; injection and token-budget semantics belong to long-term-ctx.

#### Scenario: Bound KBs are queryable per agent
- **WHEN** long-term-ctx requests the kb_ids bound to a given agent in a tenant
- **THEN** the binding store returns the agent's bound, non-archived kb_ids

#### Scenario: Bindings drive archive protection
- **WHEN** a KB has at least one row in `agent_kbs`
- **THEN** an archive attempt on that KB is blocked and the binding agents are listed

### Requirement: agent_kbs 以 agents.id 为键且引用完整
`agent_kbs` 复合键中的 `agent_id` SHALL 为整数 `agents.id`（INTEGER），并 SHALL 声明 FK→`agents.id` ON DELETE CASCADE。所有写入/查询路径（KB 侧 `/admin/kb/{kb_id}/agents`、agent 侧 `/admin/agents/{name}/kbs`、materialize 的 `list_kbs_for_agent`）SHALL 以整数 `agents.id` 为键，MUST NOT 以 `str(agent.id)` 或 agent name 寻址。binding 管理行为（绑定/解绑/双向查看/删除保护/审计）不变。

#### Scenario: agent_id 为整数且带 FK
- **WHEN** 管理库迁移运行到最新版本
- **THEN** `agent_kbs.agent_id` 为 INTEGER，且存在 FK→`agents.id` ON DELETE CASCADE

#### Scenario: agent 删除级联清理绑定
- **WHEN** 一个有 KB 绑定的 agent 被删除
- **THEN** 其 `agent_kbs` 行随 FK ON DELETE CASCADE 一并删除，不留孤儿

#### Scenario: 按整数 id 查询绑定
- **WHEN** long-term-ctx / materialize 请求某 agent 绑定的 kb_ids
- **THEN** 以整数 `agents.id` 查询 `agent_kbs`，返回该 agent 的 kb_ids（行为与改前一致，仅键类型规整）

