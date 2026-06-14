## MODIFIED Requirements

### Requirement: Managed / ad-hoc provenance badge
Each skill SHALL carry a provenance source in the `skills` master table (`source ∈ {managed, adhoc}`), not in a separate `skill_provenance` table. UI upload/create SHALL produce an `adhoc` skill. The `managed` source is reserved for a future spec-driven authoring path; until that path exists, skills SHALL default to `adhoc`. The list SHALL display the corresponding badge.

#### Scenario: UI-created skill is ad-hoc
- **WHEN** an admin uploads or creates a skill in the UI
- **THEN** its `skills.source` is `adhoc` and the list shows an "ad-hoc" badge

#### Scenario: Source stored on the catalog row
- **WHEN** the provenance source for a skill is read
- **THEN** it is returned from the `skills` master row, and no `skill_provenance` table is consulted

### Requirement: Drift marking on managed skills
Drift SHALL be tracked **per (agent, skill)** on `agent_skills.drift`, not per-skill. A runtime modification to an agent's own skill copy (via reflection or operator edit in that agent's home) SHALL be reflected as `drift=1` on that agent's binding row, set by the platform observing the agent home (never written by the agent runtime). Editing the pool's authoritative copy via the admin API SHALL NOT set per-agent drift.

#### Scenario: Runtime modification marks per-agent drift
- **WHEN** agent "support-bot" runtime-modifies its copy of skill "crm-ops"
- **THEN** the `(support-bot, crm-ops)` row in `agent_skills` has `drift=1`, while other agents' rows for "crm-ops" remain `drift=0`

#### Scenario: Editing the pool copy does not mark per-agent drift
- **WHEN** an admin edits the pool's authoritative "crm-ops" via the admin API
- **THEN** no `agent_skills.drift` flag is set by that edit

### Requirement: Immutable fields restored by spec
Fields marked immutable on a skill SHALL be recorded in `skills.immutable_fields` (JSON). The admin edit path MAY surface a notice when an immutable field is changed. The actual restore-on-deploy enforcement is deferred to the future pool-versioning / backflow change.

#### Scenario: Immutable fields read from catalog
- **WHEN** the immutable-field set for a skill is evaluated
- **THEN** it is read from `skills.immutable_fields`, not from a `skill_provenance` table

## REMOVED Requirements

### Requirement: Override reflow hooks
**Reason**: 这套 hooks（`promote` to spec / `discard` / askit `override sync`）是 no-op 占位脚手架，操作即将删除的 `skill_provenance` 表，且依赖一个尚不存在的 askit skill-authoring 上游；当前从不被有意义地触发。
**Migration**: 真正的回流调和（promote / discard / fork）将在后续 change 中基于 `reflection_management` 的 `SkillProposal` inbox 重建。本 change 移除 `POST /admin/skills/{name}/provenance/promote`、`POST /admin/skills/{name}/provenance/discard` 端点与 `askit_override()` 占位函数；运营侧在重建前无需调和操作。
