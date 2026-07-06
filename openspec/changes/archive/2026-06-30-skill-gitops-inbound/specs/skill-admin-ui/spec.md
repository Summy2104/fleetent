## MODIFIED Requirements

### Requirement: Skills managed natively in the React SPA

The React admin SPA SHALL render the skills domain natively (not a deep-link to legacy) and SHALL support, against the existing admin API: list skills, view skill content (read-only), enable / disable, manage agent bindings, view versions and version diffs, reload, and view per-skill observability. The proposals area SHALL remain **read-only** (list + diff, no approve/reject — proposal approval is agent-owned and delivered via DM).

When an external git source is configured (GitOps mode), the skills page SHALL be **content read-only**: it SHALL NOT offer create / edit / upload / archive / restore / force-publish controls (those backend endpoints return 409), SHALL show a banner indicating that skill content is authored in the external git repo (open a PR), and SHALL surface a **git sync status** card (last synced commit / time / error) with an admin "sync now" action against `/admin/skills/git/{status,sync}`.

#### Scenario: List skills and toggle enable
- **WHEN** an admin opens the skills view and enables/disables a skill
- **THEN** skills are listed via `GET /admin/skills` and the toggle calls `POST /admin/skills/{name}/enable`|`/disable`, refreshing the row

#### Scenario: GitOps mode hides content-write controls
- **WHEN** an external git source is configured and an admin opens the skills view
- **THEN** there are no create / edit / upload / archive / restore / force-publish controls, a "content authored in git" banner is shown, and a git sync status card with a "sync now" action is rendered

#### Scenario: View proposals read-only
- **WHEN** an admin opens the proposals area and selects a proposal
- **THEN** proposals are listed via `GET /admin/skills/proposals` and the diff via `GET /admin/skills/proposals/{id}/diff`, with no approve/reject controls

#### Scenario: Skills no longer deep-link to legacy
- **WHEN** the SPA navigation is rendered
- **THEN** Skills is a native route, not an entry in the legacy deep-link list
