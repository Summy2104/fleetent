# fleetent-self-managed-provenance Specification

## Purpose
TBD - created by archiving change 2026-06-02-askit-orchestration-console. Update Purpose after archive.
## Requirements
### Requirement: Provenance badge for agents and skills
Each fleetent agent / skill SHALL carry a source provenance: `spec_owned` (managed, sourced from git spec via `deploy --target fleetent`) or `db_only` (ad-hoc, created directly in the management UI). The management list SHALL show a "managed" or "ad-hoc" badge accordingly.

#### Scenario: deploy --target fleetent compiles a managed object
- **WHEN** a git spec defines agent "ops-bot", fleetent's agent_store has no such agent, and an admin runs `deploy --target fleetent` in the console
- **THEN** "ops-bot" is written into agent_store and appears in the Agent management list with a "managed" badge
- **AND** it can then be routed and invoked

#### Scenario: Ad-hoc object is not overwritten by deploy
- **WHEN** an admin created an ad-hoc agent "tmp-bot" directly in the Agent management UI and then runs `deploy --target fleetent`
- **THEN** "tmp-bot" is unaffected (the spec does not contain it, deploy neither deletes nor modifies ad-hoc objects)
- **AND** only managed objects are synced per spec

### Requirement: UI edits to managed objects create drift that can flow back
A managed object MAY still be edited in the UI for emergencies; the change SHALL be captured as an override via `override sync` and the list SHALL mark it as drift. The admin SHALL be able to view the diff in the Override Flow series and `promote` it back to spec (producing a PR), clearing the drift mark.

#### Scenario: UI edit on managed object produces drift and flows back
- **WHEN** managed agent "ops-bot" is deployed and an admin edits its `system_prompt` in the UI
- **THEN** the list marks "ops-bot" as drift
- **AND** the admin sees the diff via `override sync` in the Override Flow series, and after `promote` it flows back to spec producing a PR, and the drift mark is cleared

### Requirement: Discarded drift is restored by spec on next deploy
When an unmerged UI change (drift) on a managed object is discarded, the next `deploy --target fleetent` SHALL overwrite it with the spec content and clear the drift.

#### Scenario: Discarded drift restored from spec
- **WHEN** managed agent "ops-bot" has an unmerged UI change (drift), an admin chooses `discard` for that override, and then runs `deploy --target fleetent`
- **THEN** the UI change is overwritten and restored to the spec content and the drift is cleared

### Requirement: Immutable fields restored on deploy
Fields marked immutable on a managed object (e.g. identity / name) SHALL be restored to the spec value on the next `deploy --target fleetent`, even if changed in the UI. The UI SHALL warn at edit time that the field is spec-protected and will be restored on deploy.

#### Scenario: Immutable field restored
- **WHEN** "ops-bot" has a field marked immutable (e.g. identity), an admin changes it in the UI and then runs `deploy --target fleetent`
- **THEN** the field is force-restored to the spec value
- **AND** at edit time the UI already warned "this field is spec-protected and will be restored on deploy"

### Requirement: Ad-hoc to managed via decompile keeps identity
An ad-hoc object SHALL be promotable to managed via `decompile` (reverse-compile to spec, add to git); afterwards it becomes managed. The stable `agent_id` SHALL NOT change, so historical traces and bindings continue naturally.

#### Scenario: Ad-hoc agent promoted via decompile
- **WHEN** ad-hoc agent "tmp-bot" is validated and needs version control, and an admin runs `decompile` on it
- **THEN** a corresponding spec is generated and added to git, "tmp-bot"'s badge becomes "managed", and it is thereafter managed by spec
- **AND** its `agent_id` is unchanged so historical traces and bindings continue

### Requirement: Source switch never rebuilds the object
Switching provenance (decompile to managed, or adopt on same-name deploy) SHALL be a flag flip on the same row, preserving the stable `agent_id`. `deploy --target fleetent` hitting a same-name ad-hoc agent SHALL "adopt" it (reuse the same `agent_id`, flip to managed with UI confirmation) rather than overwrite or hard-reject.

#### Scenario: Adopt on same-name deploy reuses agent_id
- **WHEN** `deploy --target fleetent` targets an agent whose name matches an existing ad-hoc agent
- **THEN** the existing row is adopted: the same `agent_id` is reused and the row is flipped to `spec_owned` (with UI confirmation), not overwritten or rejected
- **AND** historical traces (by `agent_id`) and bindings (`user_agents` / `channel_agents` referencing `agent_id`) continue without migration

