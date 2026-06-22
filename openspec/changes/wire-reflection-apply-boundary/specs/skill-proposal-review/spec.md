## MODIFIED Requirements

### Requirement: Proposal inbox
The system SHALL expose `GET /admin/skills/proposals` aggregating the reflection domain's pending Skill change proposals (create / update / delete, status `pending`) from the unified `reflection_proposals` table (`domain='skill'`) into a review inbox. Each entry SHALL show the proposal kind, target skill, and rationale.

#### Scenario: Inbox lists pending proposals
- **WHEN** an admin opens the proposal inbox
- **THEN** the response lists each `pending` proposal with its kind (create/update/delete), target skill, and rationale

#### Scenario: Inbox excludes resolved proposals by default
- **WHEN** a proposal has been approved or rejected
- **THEN** it is excluded from the default inbox view

## ADDED Requirements

### Requirement: Skill proposal application
当一个 `approved` 状态的 Skill 提案被 resolve 为 apply 时，系统 SHALL 经 Skill 管理边界真正落地该提案——
对 create/update 提案执行 `write_skill`（含 provenance）并 `reload` skill registry，对 deprecate 提案写入禁用后的
SKILL.md 并 reload。系统 SHALL NOT 让 apply 停在未配置的占位实现（不得 `raise "boundary is not configured"`）。
此应用边界 SHALL 有单一真相源实现，被 reflection 审批门复用，无论调用经由 public reflection API 路径还是 gate 本地
fallback 路径，应用动作 SHALL 使用同一份边界实现。

#### Scenario: Approved skill proposal applies through the boundary
- **WHEN** 一个 `approved` 的 create/update Skill 提案被 apply
- **THEN** 对应 skill 经 `write_skill` 写入并 registry reload，提案状态变为 `applied`

#### Scenario: Apply boundary is never an unconfigured stub
- **WHEN** skill 提案 apply 走 gate 的 fallback 路径（reflection state_db 未注入）
- **THEN** apply 委托到真实边界实现，不抛 "boundary is not configured" 占位错误
