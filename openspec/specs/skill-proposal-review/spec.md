# skill-proposal-review Specification

## Purpose
TBD - created by archiving change 2026-06-02-skill-management. Update Purpose after archive.
## Requirements
### Requirement: Proposal inbox
The system SHALL expose `GET /admin/skills/proposals` aggregating the reflection domain's pending Skill change proposals (create / update / delete, status `pending`) from the unified `reflection_proposals` table (`domain='skill'`) into a review inbox. Each entry SHALL show the proposal kind, target skill, and rationale.

#### Scenario: Inbox lists pending proposals
- **WHEN** an admin opens the proposal inbox
- **THEN** the response lists each `pending` proposal with its kind (create/update/delete), target skill, and rationale

#### Scenario: Inbox excludes resolved proposals by default
- **WHEN** a proposal has been approved or rejected
- **THEN** it is excluded from the default inbox view

### Requirement: Skill proposal application
When an `approved` Skill proposal is resolved as apply, the system SHALL apply it through the Skill management boundary.
For create/update proposals it SHALL execute `write_skill` (with provenance) and reload the skill registry.
For deprecate proposals it SHALL write the disabled `SKILL.md` form and reload the registry.
The system SHALL NOT stop at an unconfigured placeholder implementation, and both the public reflection API path and the gate fallback path SHALL reuse the same boundary implementation as the single source of truth.

#### Scenario: Approved skill proposal applies through the boundary
- **WHEN** an `approved` create or update Skill proposal is applied
- **THEN** the corresponding skill is written via `write_skill`, the registry reloads, and the proposal status becomes `applied`

#### Scenario: Apply boundary is never an unconfigured stub
- **WHEN** a Skill proposal apply runs through the gate fallback path because reflection state DB is not injected
- **THEN** the apply flow delegates to the real boundary implementation and does not raise a `"boundary is not configured"` placeholder error

### Requirement: Proposal diff
For each proposal the system SHALL present a change diff computed by comparing the reflection snapshot against the skill's current content.

#### Scenario: Diff shown from snapshot vs current
- **WHEN** an admin opens an `update` proposal
- **THEN** the response contains a diff between the reflection snapshot and the skill's current content
