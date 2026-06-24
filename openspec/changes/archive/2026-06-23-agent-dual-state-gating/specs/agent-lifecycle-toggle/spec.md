# agent-lifecycle-toggle Specification (delta)

## ADDED Requirements

### Requirement: New agents start disabled

A newly created or cloned agent SHALL start with `status=disabled`. 控制台 `create` 与 `clone` SHALL 显式落 `disabled`，使新 agent 在被显式 enable 之前不进入任何 node 的期望态拉取（`node-desired-state-api` 按 `status=="enabled"` 过滤）。这避免「enabled 但未绑定 node、不会被任何 node 拉起」的误导态。

#### Scenario: Created agent is disabled until enabled
- **WHEN** an admin creates a new agent via the console
- **THEN** its `agent_admin_state.status` is `disabled`
- **AND** it does not appear in any node's desired-state pull until explicitly enabled

#### Scenario: Cloned agent is disabled
- **WHEN** an admin clones an agent
- **THEN** the clone's `status` is `disabled` (no bindings carried over)

### Requirement: Enable requires a bound node

The `enable` transition SHALL be gated on node placement: an agent SHALL only be enabled when it is pinned to a node (`agent_placements` row exists). Attempting to enable an agent with no placement SHALL be rejected without changing `status`. `disable` SHALL NOT be gated. `restore` (un-archive) is out of this requirement's scope and retains its existing behavior.

#### Scenario: Enable rejected without a bound node
- **WHEN** an admin requests `enable` for an agent that has no `agent_placements` row
- **THEN** the request is rejected (409, detail `agent not bound to a node`) and `status` is unchanged

#### Scenario: Enable allowed once pinned
- **WHEN** the agent is pinned to a node and an admin requests `enable`
- **THEN** `status` becomes `enabled`

#### Scenario: Disable is never gated
- **WHEN** an admin requests `disable` for an agent (bound or not)
- **THEN** `status` becomes `disabled`
