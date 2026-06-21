# skill-admin-ui Specification

## Purpose
TBD - created by syncing change add-admin-console-modules. Update Purpose after archive.
## Requirements
### Requirement: Skills management tab
The admin console SHALL present a Skills tab listing each skill with its status (enabled/disabled), and SHALL provide a "reload skills" control. The tab SHALL be visible to all signed-in roles; write controls SHALL be admin-only.

#### Scenario: Admin sees skills list
- **WHEN** an admin opens the Skills tab
- **THEN** each skill's name and enabled state are shown via `GET /admin/skills`

#### Scenario: Viewer cannot mutate skills
- **WHEN** a viewer opens the Skills tab
- **THEN** create / edit / enable / disable / delete / reload controls are hidden

### Requirement: Skill lifecycle and binding actions
The console SHALL let an admin create, edit, enable, disable, delete, and restore a skill, bind/unbind agents, force-publish, and view observability, each calling the matching `/admin/skills` endpoint.

#### Scenario: Enable a skill
- **WHEN** an admin clicks enable on a disabled skill
- **THEN** the console calls `POST /admin/skills/{name}/enable` and the row reflects enabled

#### Scenario: Bind an agent to a skill
- **WHEN** an admin binds an agent to a skill
- **THEN** the console calls `PUT /admin/skills/{name}/agents/{agent_id}` and the binding appears

### Requirement: Skill proposal review
The console SHALL list skill proposals and let an admin view a proposal diff. Approve / reject are not offered from the console: proposal approval is agent-owned and delivered to the approver via DM, with the console acting as a read-only projection.

#### Scenario: List and view a proposal diff
- **WHEN** an admin opens the skill proposals list and selects a proposal
- **THEN** the console lists proposals via `GET /admin/skills/proposals` and renders the diff via `GET /admin/skills/proposals/{id}/diff`, with no approve/reject controls
