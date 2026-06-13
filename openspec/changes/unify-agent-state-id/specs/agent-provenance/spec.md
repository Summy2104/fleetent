# agent-provenance Delta

## ADDED Requirements

### Requirement: agent_admin_state 以 agents.id 为键且引用完整
`agent_admin_state`（agent 控制台 status / provenance / drift 态）SHALL 以 `agent_id`（INTEGER，= `agents.id`）为键，并 SHALL 声明 FK→`agents.id` ON DELETE CASCADE（agent 删除时其控制台状态行级联清理）。MUST NOT 以 agent name 为键。status / provenance / drift 的取值与翻转语义不变；HTTP/CLI 按 `{name}` 寻址时 MUST 先解析 name→`agents.id`。

#### Scenario: admin_state 键为整数 agent_id + FK
- **WHEN** 管理库迁移运行到最新版本
- **THEN** `agent_admin_state` 以 `agent_id`（INTEGER）为键，存在 FK→`agents.id` ON DELETE CASCADE，且不以 agent name 为键

#### Scenario: agent 删除级联清理控制台态
- **WHEN** 一个 agent 被删除
- **THEN** 其 `agent_admin_state` 行随 FK ON DELETE CASCADE 一并删除，不留孤儿

#### Scenario: 翻转 status/provenance 不重建 agent
- **WHEN** 经控制台翻转某 agent 的 status 或 provenance
- **THEN** 仅更新该 agent_id 对应行，agent 定义/绑定/历史不受影响（行为与改键前一致）
