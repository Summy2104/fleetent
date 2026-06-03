# agent-admin-ui Specification

## Purpose
TBD - created by syncing change add-admin-console-modules. Update Purpose after archive.
## Requirements
### Requirement: Agents management tab
The admin console SHALL present an Agents tab listing each agent with its status, and SHALL list available agent templates. Write controls SHALL be admin-only.

#### Scenario: Admin sees agents and templates
- **WHEN** an admin opens the Agents tab
- **THEN** agents are listed via `GET /admin/agents` and templates via `GET /admin/agent-templates`

#### Scenario: Viewer cannot mutate agents
- **WHEN** a viewer opens the Agents tab
- **THEN** enable / disable / archive / restore / clone / bind controls are hidden

### Requirement: Agent lifecycle and clone
The console SHALL let an admin enable, disable, archive, restore, and clone an agent, and view observability, calling the matching endpoints.

#### Scenario: Clone an agent
- **WHEN** an admin clones an agent
- **THEN** the console calls `POST /admin/agents/{name}/clone` and the new agent appears

### Requirement: Agent versions and bindings
The console SHALL show an agent's versions and let an admin activate a version, and bind/unbind users and channels.

#### Scenario: Activate a version
- **WHEN** an admin activates a listed version
- **THEN** the console calls `POST /admin/agents/{name}/versions/{version}/activate`

#### Scenario: Bind a user to an agent
- **WHEN** an admin binds a user to an agent
- **THEN** the console calls `POST /admin/agents/{name}/bindings/users/{user_id}`
