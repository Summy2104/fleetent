## ADDED Requirements

### Requirement: Clone an agent without bindings
An admin SHALL be able to clone an existing agent under a new globally unique name. The clone SHALL copy the source agent's active version definition (system_prompt, allowed_tools, model_overrides, skills_dir, mcp_server_ids, memory_namespace) and SHALL NOT copy any user or channel bindings or the default flag. The clone SHALL start in `status=enabled` and `provenance=adhoc`.

#### Scenario: Clone copies definition, not bindings
- **WHEN** "ops-bot" is bound to several channels and an admin clones it as "ops-bot-staging"
- **THEN** "ops-bot-staging" has the same system_prompt, allowed_tools, and model config as "ops-bot"'s active version
- **AND** "ops-bot-staging" has no `user_agents` or `channel_agents` rows and is not the default agent
- **AND** "ops-bot-staging" is `enabled`

#### Scenario: Clone with duplicate name rejected
- **WHEN** an admin clones "ops-bot" using a name that already exists and is not archived
- **THEN** the request is rejected (409) and nothing is persisted

#### Scenario: Clone is audited
- **WHEN** a clone succeeds
- **THEN** an `agent.clone` audit entry records the source and the new agent id

### Requirement: Built-in template library
The system SHALL expose a read-only built-in template library containing at least the templates `readonly-qa`, `ops`, and `support`, each carrying a display name, recommended `allowed_tools`, and a `system_prompt`. Templates SHALL NOT be stored in the database and SHALL NOT be editable via the management API.

#### Scenario: List templates
- **WHEN** an admin requests the template list
- **THEN** the response includes at least `readonly-qa`, `ops`, and `support` entries, each with id, display name, allowed_tools, and a system_prompt preview

#### Scenario: Create agent from template prefills fields
- **WHEN** an admin starts a new agent from the `readonly-qa` template
- **THEN** the create form is prefilled with the template's `allowed_tools` and `system_prompt`
- **AND** after adjusting only the name, the admin can save and the new agent is created with the template's fields

#### Scenario: Templates are read-only
- **WHEN** any request attempts to modify or delete a built-in template
- **THEN** the request is rejected and the template library is unchanged
