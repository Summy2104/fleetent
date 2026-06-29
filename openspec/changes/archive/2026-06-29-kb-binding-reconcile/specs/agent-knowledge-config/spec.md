## MODIFIED Requirements

### Requirement: Agent knowledge bindings

`agent.yaml` SHALL define Agent-side knowledge access under `knowledge`, not under
`knowledge_base`. The Agent-side config SHALL contain bindings to KB ids and retrieval policy,
but SHALL NOT contain KB source connector construction details such as Google Drive folders or
Confluence spaces. `knowledge.bindings[]` 是运行时绑定的真相载体(快照),由 platform 从 `agent_kbs`
materialize;运行时 SHALL NOT 由 agent 直接查询 `agent_kbs`(保解耦)。该快照 SHALL 经 reconcile 与
`agent_kbs` 保持同步:bind/unbind 后受影响 agent 的 bindings SHALL 被重新 materialize,并在 agent 的
**下一个 session 边界**生效,不在进行中的对话中途改变 KB 范围。

#### Scenario: Agent binds to one or more KBs
- **WHEN** an Agent config declares `knowledge.enabled: true`
- **THEN** it must declare at least one `knowledge.bindings[]` entry with `tenant_id` and `kb_id`

#### Scenario: Agent has one default KB at most
- **WHEN** multiple `knowledge.bindings[]` entries are declared
- **THEN** at most one entry may have `default: true`

#### Scenario: Old source connector nesting is not accepted
- **WHEN** an Agent config declares `knowledge_base.google_drive.connectors[]` or
  `knowledge_base.confluence.connectors[]`
- **THEN** Agent config loading fails loudly

#### Scenario: Bind change is materialized and takes effect at session boundary
- **WHEN** 管理员在 platform bind 或 unbind 改了某 agent 的 `agent_kbs`
- **THEN** 受影响 agent 的 `knowledge.bindings` 经 reconcile 从 `agent_kbs` 重新 materialize
- **AND** 更新后的 bindings 在该 agent 的下一个 session 边界生效
- **AND** 进行中的对话不改变其 KB 检索范围

#### Scenario: Running agent does not query agent_kbs directly
- **WHEN** agent 运行时确定其可检索 KB 范围
- **THEN** 它读取自身 agent.yaml 的 `knowledge.bindings` 快照
- **AND** 不查询管理库 `agent_kbs`(无 platform DB 环境下仍可运行)

## ADDED Requirements

### Requirement: Agent knowledge bindings are single-tenant

一个 agent 的所有 `knowledge.bindings[]` SHALL 共享该 agent 的 `tenant_id`。materialize 与 agent config 加载 SHALL 校验该不变量,违反时 SHALL fail loudly,而非静默只取第一个 binding 的 tenant。

#### Scenario: All bindings share the agent tenant
- **WHEN** materialize 或加载一个 agent 的 knowledge bindings
- **THEN** 每条 binding 的 `tenant_id` 等于该 agent 的 `tenant_id`

#### Scenario: Cross-tenant binding is rejected
- **WHEN** 某 agent 的 bindings 含与 agent `tenant_id` 不一致的条目
- **THEN** 系统 fail loudly,不静默忽略或只取第一个
