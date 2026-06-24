# agent-admin-ui Specification (delta)

## ADDED Requirements

### Requirement: Agents tab surfaces desired and runtime state

The Agents tab SHALL display, for each agent, both its **desired state**（`status`：enabled / disabled / archived）and its **runtime state**（来自响应的 `runtime` 投影：`phase` running/stopped、`health`、所在 `node_id`）。当 `runtime` 为 `null`（node 未上报）时 SHALL 呈现一个明确的「未运行 / 无上报」态，而非留空或显示陈旧值。绑定信息（`placement`：所在 node 或未绑定）SHALL 一并可见。

#### Scenario: Card shows desired and runtime state
- **WHEN** an agent's list/detail response carries `status="enabled"` and `runtime={phase:"running", health, node_id}`
- **THEN** the card shows both the desired status and the runtime phase/health and the node it runs on

#### Scenario: No runtime report renders an explicit not-running state
- **WHEN** an agent's `runtime` is `null`
- **THEN** the card shows an explicit not-running / no-report indication (not a blank or stale value)

### Requirement: Enable control is gated on node binding

When an agent is `disabled` and not bound to a node (`placement` is `null`), the Agents tab SHALL render the「Enable」control as **disabled** and SHALL surface the reason（提示管理员需先把 agent pin 到某个 node 才能启用）。当 `placement` 非空时「Enable」SHALL 可操作。「Disable」控件 SHALL NOT 受此约束。

#### Scenario: Enable disabled with a hint when unbound
- **WHEN** an agent is `disabled` and its `placement` is `null`
- **THEN** the「Enable」control is disabled and a reason hint is shown (must be pinned to a node first)

#### Scenario: Enable actionable once bound
- **WHEN** an agent is `disabled` and its `placement` is non-null
- **THEN** the「Enable」control is actionable and triggers `POST /admin/agents/{name}/enable`
