# skill-proposal-review Specification

## Purpose
TBD - created by archiving change 2026-06-02-skill-management. Update Purpose after archive.
## Requirements
### Requirement: Proposal inbox
The system SHALL expose `GET /admin/skills/proposals` aggregating the reflection domain's pending Skill change proposals (create / update / delete, status `pending`) from `skill_proposals` into a review inbox. Each entry SHALL show the proposal kind, target skill, and rationale.

#### Scenario: Inbox lists pending proposals
- **WHEN** an admin opens the proposal inbox
- **THEN** the response lists each `pending` proposal with its kind (create/update/delete), target skill, and rationale

#### Scenario: Inbox excludes resolved proposals by default
- **WHEN** a proposal has been approved or rejected
- **THEN** it is excluded from the default inbox view

### Requirement: Proposal diff
For each proposal the system SHALL present a change diff computed by comparing the reflection snapshot against the skill's current content.

#### Scenario: Diff shown from snapshot vs current
- **WHEN** an admin opens an `update` proposal
- **THEN** the response contains a diff between the reflection snapshot and the skill's current content

