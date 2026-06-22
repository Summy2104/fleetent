## ADDED Requirements

### Requirement: Skills managed natively in the React SPA

The React admin SPA SHALL render the skills domain natively (not a deep-link to legacy) and SHALL support, against the existing admin API: list skills, view skill content, enable / disable, delete / restore, force-publish, reload, manage agent bindings, and view versions and version diffs. The proposals area SHALL be **read-only** — list proposals and view a proposal diff; it SHALL NOT offer approve/reject (proposal approval is agent-owned and delivered via DM).

#### Scenario: List skills and toggle enable

- **WHEN** an admin opens the skills view and enables/disables a skill
- **THEN** skills are listed via `GET /admin/skills` and the toggle calls `POST /admin/skills/{name}/enable`|`/disable`, refreshing the row

#### Scenario: View proposals read-only

- **WHEN** an admin opens the proposals area and selects a proposal
- **THEN** proposals are listed via `GET /admin/skills/proposals` and the diff via `GET /admin/skills/proposals/{id}/diff`, with no approve/reject controls

#### Scenario: Skills no longer deep-link to legacy

- **WHEN** the SPA navigation is rendered
- **THEN** Skills is a native route, not an entry in the legacy deep-link list
