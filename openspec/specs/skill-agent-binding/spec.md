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

由于 agent 运行时只读 `agent.yaml`、从不访问 platform DB，`agent_skills` 绑定矩阵 SHALL 在 materialize 时被转换为 `AgentFile.allowed_skills`。`agent_file_from_store()` SHALL 用 `has_any_binding(agent.id)` 判定该 agent 是否有绑定行（`agent.id` 为整数，不再 `str()` 包装）：

- 有绑定行：`allowed_skills` SHALL 恰好为 `enabled_skill_names(agent.id)` 的内容（enabled=1 子集），即使该集合为空（表示该 agent 被显式收窄到无 skill）
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

### Requirement: agent_skills 以 agents.id 为键且引用完整
`agent_skills` 的 `agent_id` 列 SHALL 为整数 `agents.id`（INTEGER），并 SHALL 声明 FK→`agents.id` ON DELETE CASCADE（agent 删除时其绑定行级联清理）。除绑定列（`enabled`）外，`agent_skills` SHALL 额外承载 **per-agent 部署态**列：`base_version`（该 agent 该 skill 物化自的池版本）、`drift`（这个 agent 副本是否分叉，默认 0）、`drift_at`（漂移观测时间）。所有写入路径——skill 侧（`/admin/skills/{name}/agents`）与 agent 侧（`/admin/agents/{name}/skills/{skill}`）——SHALL 一致以 `agents.id` 为键落行；HTTP 路由按 `{name}` 寻址时 MUST 先解析 name→`agents.id` 再写 store。由此**任一 admin 路径设置的绑定，对运行时 materialize（按 `agents.id` 读）均可见**，消除此前 agent 侧按 name 写、materialize 按 id 读导致绑定静默失效的缺陷。

#### Scenario: agent_id 为整数且带 FK
- **WHEN** 管理库迁移运行到最新版本
- **THEN** `agent_skills.agent_id` 为 INTEGER，且存在 FK→`agents.id` ON DELETE CASCADE

#### Scenario: agent_skills 承载 per-agent 部署态列
- **WHEN** 管理库迁移运行到最新版本
- **THEN** `agent_skills` 含 `base_version` / `drift`（默认 0）/ `drift_at` 列

#### Scenario: 控制台设的绑定 materialize 可见（bug 修复）
- **WHEN** 经 agent 侧路由 `PUT /admin/agents/support-bot/skills/crm-ops {enabled:true}` 启用绑定，随后该 agent materialize
- **THEN** 该绑定以 `agents.id` 落行，materialize 按 `agents.id` 读到它，`crm-ops` 进入 `allowed_skills`

#### Scenario: 两侧路径键一致
- **WHEN** 同一 agent 的绑定分别经 skill 侧与 agent 侧路由写入
- **THEN** 两者落在同一 `(agents.id, skill_name)` 键上，不产生 name-keyed 与 id-keyed 两套行

#### Scenario: agent 删除级联清理绑定
- **WHEN** 一个 agent 被删除
- **THEN** 其 `agent_skills` 行随 FK ON DELETE CASCADE 一并删除，不留孤儿

