# kb-agent-binding Delta

## ADDED Requirements

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
