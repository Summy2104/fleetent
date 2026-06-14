## MODIFIED Requirements

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
