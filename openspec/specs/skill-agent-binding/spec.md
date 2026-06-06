# skill-agent-binding Specification

## Purpose
TBD - created by archiving change 2026-06-02-skill-management. Update Purpose after archive.
## Requirements
### Requirement: Skill-to-Agent matrix
The system SHALL maintain a Skill ↔ Agent binding (`agent_skills`) expressing which skills are available to which agent. The binding SHALL be editable both from an agent's detail (selecting available skills) and from a skill's detail (viewing/adjusting the agents that enable it), backed by the same reference view.

#### Scenario: List agents enabling a skill
- **WHEN** an admin sends `GET /admin/skills/{name}/agents`
- **THEN** the response lists every agent and whether it has the skill enabled

#### Scenario: Edit binding from agent side
- **WHEN** an admin enables skill "crm-ops" for agent "support-bot"
- **THEN** an `agent_skills` row with `enabled=1` is recorded for `(support-bot, crm-ops)` and the action is audited

### Requirement: Agent-centric skill binding read and edit

The system SHALL expose an agent-centric view of skill bindings. `GET
/admin/agents/{name}/skills` SHALL return every known skill paired with whether it is
enabled for that agent. `PUT /admin/agents/{name}/skills/{skill_name}` with body
`{enabled: bool}` SHALL upsert the `agent_skills` row for `(agent, skill)` and audit
the action. These routes operate on the same `agent_skills` matrix used by the
skill-side routes.

#### Scenario: Read skills for an agent

- **WHEN** an admin sends `GET /admin/agents/support-bot/skills`
- **THEN** the response lists every known skill with an `enabled` flag for "support-bot"

#### Scenario: Enable a skill from the agent side

- **WHEN** an admin sends `PUT /admin/agents/support-bot/skills/crm-ops` with `{enabled: true}`
- **THEN** an `agent_skills` row with `enabled=1` is recorded for `(support-bot, crm-ops)` and the action is audited

### Requirement: Per-agent enable/disable
The system SHALL allow disabling a skill at the agent level (`agent_skills.enabled=0`)
independent of its global state. A skill disabled for one agent SHALL NOT be injected
for that agent while other agents that enable it continue to inject it normally. At
agent invocation, when an agent has at least one `agent_skills` row, the effective
injectable skill set SHALL be exactly the enabled (`enabled=1`) subset; when an agent
has no `agent_skills` rows at all, the runtime SHALL fall back to all skills discovered
in the agent's `skills_dir`.

#### Scenario: Per-agent disable is scoped
- **WHEN** skill "crm-ops" is globally enabled but disabled for agent "support-bot", and a request that would trigger it arrives via "support-bot"
- **THEN** "support-bot" does not inject "crm-ops" while other agents that enable it still inject it normally
- **AND** the disable action is audited

#### Scenario: Unbound agent injects all skills

- **WHEN** agent "support-bot" has no `agent_skills` rows and a request that would trigger a discovered skill arrives
- **THEN** the skill is injected (fallback to all skills in `skills_dir`)

#### Scenario: Bound agent injects only enabled skills

- **WHEN** agent "support-bot" has `agent_skills` rows and only "crm-ops" is `enabled=1`
- **THEN** only "crm-ops" is eligible for injection for "support-bot", even if other skills match

### Requirement: Reference view reused for deletion protection
The same `agent_skills` reference view SHALL be the source for archival reference protection — querying which agents still have a skill enabled (`enabled=1`).

#### Scenario: Reference view reports occupying agents
- **WHEN** archival of a skill is attempted
- **THEN** the reference view returns the agents with `enabled=1`, which the archive endpoint uses to block deletion when non-empty

### Requirement: Materialize 将 agent_skills 绑定写入 agent.yaml 的 allowed_skills

由于 agent 运行时只读 `agent.yaml`、从不访问 platform DB，`agent_skills` 绑定矩阵 SHALL 在 materialize 时被转换为 `AgentFile.allowed_skills`。`agent_file_from_store()` SHALL 用 `has_any_binding(str(agent.id))` 判定该 agent 是否有绑定行：

- 有绑定行：`allowed_skills` SHALL 恰好为 `enabled_skill_names(str(agent.id))` 的内容（enabled=1 子集），即使该集合为空（表示该 agent 被显式收窄到无 skill）
- 无绑定行：`allowed_skills` SHALL 回退到 authored 的 `agent.allowed_skills`

#### Scenario: 有绑定时 allowed_skills 取 enabled 子集

- **WHEN** agent "support-bot" 在 `agent_skills` 中有 `(support-bot, crm-ops, enabled=1)` 和 `(support-bot, billing, enabled=0)`，触发 materialize
- **THEN** 产出的 agent.yaml 中 `allowed_skills` 恰好为 `["crm-ops"]`

#### Scenario: 绑定全部关闭时 allowed_skills 为空

- **WHEN** agent "support-bot" 在 `agent_skills` 中所有行的 `enabled` 均为 0，触发 materialize
- **THEN** 产出的 agent.yaml 中 `allowed_skills` 为空列表（catalog 收窄到无 skill）
- **AND** 不回退到 authored 的 allowed_skills

#### Scenario: 无绑定时回退 authored 值

- **WHEN** agent "support-bot" 在 `agent_skills` 中没有任何行，且其 authored `allowed_skills` 为 `["jira"]`，触发 materialize
- **THEN** 产出的 agent.yaml 中 `allowed_skills` 为 `["jira"]`

