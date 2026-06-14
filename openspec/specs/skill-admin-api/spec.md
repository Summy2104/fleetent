# skill-admin-api Specification

## Purpose
TBD - created by archiving change 2026-06-02-skill-management. Update Purpose after archive.
## Requirements
### Requirement: Skill list and search
The system SHALL expose `GET /admin/skills` returning all skills with name, one-line description, tags/platforms, enablement state (globally enabled / globally disabled / archived), latest security-audit verdict (pass / suspicious / rejected), cumulative injection hits, last-triggered time, and which agents enable it. Each entry SHALL also include the provenance `source` (read from the `skills` master row) and a **per-agent drift summary** (e.g. the count or list of agents whose deployed copy has `drift=1`), replacing any per-skill drift flag. The list SHALL support search and sort by name, tag, state, and audit verdict.

#### Scenario: List returns skill metadata
- **WHEN** an admin or viewer sends `GET /admin/skills`
- **THEN** the response is a JSON array where each entry contains name, description, tags, platforms, enablement state, audit verdict, injection hit count, last-triggered time, enabling agents, provenance `source`, and a per-agent drift summary
- **AND** archived skills are excluded by default

#### Scenario: Search by audit verdict
- **WHEN** `GET /admin/skills?audit=suspicious` is sent
- **THEN** only skills whose latest audit verdict is `suspicious` are returned

#### Scenario: Drift summary reflects per-agent state
- **WHEN** skill "crm-ops" is drifted on agent "support-bot" but not on others, and `GET /admin/skills` is sent
- **THEN** "crm-ops" entry's drift summary reports exactly the drifted agent(s), not a single per-skill flag

### Requirement: Upload or create with frontmatter validation and audit gating
The system SHALL expose `POST /admin/skills` to upload a `SKILL.md` (or a directory package with scripts/templates) or create one inline. Before publishing, the system SHALL validate the YAML frontmatter and invoke the skill domain's security audit, then gate the outcome by verdict: a `rejected` verdict SHALL NOT publish and SHALL quarantine the skill; a `suspicious` verdict SHALL publish with a list mark; a `pass` verdict SHALL publish. Publishing SHALL trigger a hot reload.

#### Scenario: Valid skill publishes and takes effect immediately
- **WHEN** an admin uploads a skill with valid frontmatter that passes the security audit
- **THEN** the skill is published, a hot reload is triggered, it appears in the list, and it is matchable for subsequent requests without a service restart
- **AND** the upload action is audited

#### Scenario: Injection-flagged skill is quarantined, not published
- **WHEN** an admin uploads a skill whose content triggers a `rejected`-level audit rule
- **THEN** the skill is not published and enters quarantine, the response lists the matched injection patterns, the skill participates in no matching/injection, and the event is audited

#### Scenario: Suspicious skill publishes but is marked
- **WHEN** an admin uploads a skill that triggers a `suspicious`-level rule
- **THEN** the skill is published and matchable but marked "suspicious" in the list, and the detail view shows the matched rules for review

#### Scenario: Invalid frontmatter rejected
- **WHEN** the uploaded skill has malformed or incomplete YAML frontmatter
- **THEN** the response is 422 with the validation error, the skill is not published, and nothing is persisted

### Requirement: Edit skill
The system SHALL expose `PUT /admin/skills/{name}` to edit frontmatter (name / description / tags / platforms / `exclusive` etc.) and body content. On save it SHALL re-run the security audit and trigger a hot reload; the edit SHALL apply to subsequent requests while in-flight sessions are unaffected.

#### Scenario: Edit re-audits and hot reloads
- **WHEN** an admin edits a published skill's body and saves
- **THEN** the security audit re-runs, a hot reload is triggered, subsequent requests use the new content, and the action is audited

### Requirement: Global enable/disable
The system SHALL expose endpoints to globally enable or disable a skill. A globally disabled skill SHALL NOT be matched or injected for any agent; the action SHALL be audited; re-enabling SHALL restore matching.

#### Scenario: Global disable stops injection
- **WHEN** an admin globally disables skill "crm-ops"
- **THEN** subsequent requests no longer match/inject "crm-ops", the action is audited, and re-enabling restores matching

### Requirement: Archive (soft delete) with reference protection and restore
Deletion SHALL be a soft delete (archive). The system SHALL block archival when any agent still explicitly enables the skill, listing the occupying agents. Once archived, the skill SHALL stop participating in matching/injection, be hidden from the list, retain its file snapshot and historical hit traces, and be restorable within a retention window. Archival SHALL require a second confirmation.

#### Scenario: Archive blocked while an agent enables it
- **WHEN** an admin attempts to delete skill "crm-ops" while at least one agent still explicitly enables it
- **THEN** the deletion is blocked, the response lists the enabling agents and asks to disable first, and nothing is persisted

#### Scenario: Archive succeeds and is restorable
- **WHEN** no agent enables skill "crm-ops" and the admin deletes it with a second confirmation
- **THEN** the skill is marked archived, stops participating in matching/injection, its file snapshot and historical traces are retained, and it is restorable within the retention window

### Requirement: Security audit display and quarantine force-publish
The list and detail views SHALL show each skill's latest audit verdict and matched rules. A `rejected` skill SHALL stay in quarantine and not be injected until an admin explicitly force-publishes it; force-publish SHALL require a second confirmation and SHALL be audited.

#### Scenario: Quarantined skill not injected
- **WHEN** a skill's latest verdict is `rejected`
- **THEN** it is shown in quarantine, participates in no injection, and viewers cannot operate on it

#### Scenario: Force-publish requires confirmation and audit
- **WHEN** an admin force-publishes a quarantined skill with a second confirmation
- **THEN** the skill is published, retains a "suspicious (forced)" mark for ongoing review, and the action is audited

### Requirement: Hot reload trigger
The system SHALL expose a "rescan skills/" trigger equivalent to the skill domain's hot reload. During rescan the old index SHALL continue serving; on success the index is switched atomically; on failure the old index is retained and the UI is warned.

#### Scenario: Rescan applies new and changed skills
- **WHEN** an admin has added/changed files under `skills/` and clicks rescan
- **THEN** after the index rebuilds the new/changed skills take effect for subsequent requests, the old index keeps serving during rescan, and on scan failure the old index is retained with a UI warning

### Requirement: Per-skill observability view
The skill detail view SHALL surface, sourced from observability, that skill's hit/injection counts, the sessions that triggered it, and whether it has been triggered over the last N days, highlighting long-zero-trigger skills; it SHALL allow drill-down into a single-session trace. This view SHALL be a per-skill aggregation only and SHALL NOT store traces.

#### Scenario: Aggregated per-skill metrics
- **WHEN** an admin opens a skill's observability view
- **THEN** the response contains that skill's hit/injection counts, triggering sessions, and recent-trigger status, with long-zero-trigger highlighted, drawing data from observability without persisting traces

### Requirement: Skill management permissions and audit
Upload / edit / enable-disable / archive / per-agent assignment / proposal review / force-publish SHALL be admin-only; viewers MAY only browse the list, audit verdicts, and observability. High-risk actions SHALL require a second confirmation, and all write actions SHALL be audited (who / when / which skill / what).

#### Scenario: Viewer cannot manage skills
- **WHEN** a viewer attempts to upload / edit / enable-disable / archive a skill or review a proposal
- **THEN** the action returns 403, nothing is persisted, and the viewer can only browse the list, audit verdicts, and observability

#### Scenario: Unauthenticated rejected
- **WHEN** a request to any `/admin/skills/*` write endpoint carries no valid session
- **THEN** the response is 401

### Requirement: Skill 写操作触发受影响 agent 的 re-materialize

由于 agent 运行时只读 agent.yaml、不访问 platform DB，skill 管理的写操作 SHALL 在写 DB 后触发受影响 agent 的 re-materialize，把最新决策落到各 agent 的 agent.yaml。触发是 best-effort：单个 agent 的 re-materialize 失败 SHALL 被记录但不阻断接口响应或其余 agent 的刷新。

- 全局 enable/disable（`POST /admin/skills/{name}/enable|disable`）影响所有 agent 的 `disabled_skills`，SHALL 触发全量 re-materialize
- per-agent 绑定（`PUT /admin/skills/{name}/agents/{agent_id}`）只影响该 agent 的 `allowed_skills`，SHALL 只 re-materialize 该 agent

#### Scenario: 全局 disable 触发全量 re-materialize

- **WHEN** admin 调用 `POST /admin/skills/crm-ops/disable`
- **THEN** DB 中该 skill 的 `global_enabled` 置为 0，写审计日志
- **AND** 所有 authored agent 的 agent.yaml 被重新导出（best-effort）

#### Scenario: per-agent 绑定只 re-materialize 对应 agent

- **WHEN** admin 调用 `PUT /admin/skills/crm-ops/agents/{id}` 设置某 agent 的绑定
- **THEN** 该 agent 的 agent.yaml 被重新导出
- **AND** 其他 agent 的 agent.yaml 不被触碰

#### Scenario: 单个 agent re-materialize 失败不阻断接口

- **WHEN** 全量 re-materialize 过程中某个 agent 导出失败（如缺 provider 配置）
- **THEN** 该失败被记录为结构化告警，接口仍返回成功，其余 agent 正常刷新

### Requirement: Skill 命中追踪提供真实 observability 数据

每次 `read_skill` 成功加载一个 skill 的全文 MUST 记录一条命中（skill 名、可得的 agent / session、时间戳）到持久化存储。per-skill observability 查询 MUST 据此返回真实数据——命中计数与触发它的去重 session 列表，且 `stale` MUST 为假——而非固定的空占位符。

命中记录 MUST 为 best-effort：记录写入失败（DB 不可用等）SHALL 被捕获并记录告警，MUST NOT 阻断 `read_skill` 返回 skill 正文。被拒绝（audit_blocked）或未知名的 read_skill 调用 MUST NOT 记为命中。

#### Scenario: read_skill 成功加载记一次命中
- **WHEN** 对一个可用 skill 成功调用 `read_skill`
- **THEN** 存储中新增一条该 skill 的命中记录（含可得的 agent/session 与时间戳）

#### Scenario: observability 返回真实命中与 session
- **WHEN** 某 skill 已被 read_skill 加载若干次（来自不同 session），admin 查询其 observability
- **THEN** 返回真实命中计数与触发它的去重 session 列表，`stale` 为假

#### Scenario: 命中记录失败不阻断 read_skill
- **WHEN** `read_skill` 成功加载 skill 但命中记录写入抛异常
- **THEN** 异常被捕获并记录告警，`read_skill` 仍返回 skill 正文

#### Scenario: 拒绝与未知名不记命中
- **WHEN** `read_skill` 因 audit_blocked 被拒，或因未知 skill 名返回错误
- **THEN** 不记录命中

