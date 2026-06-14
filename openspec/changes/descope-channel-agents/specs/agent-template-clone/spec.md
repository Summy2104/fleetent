# agent-template-clone Delta

## MODIFIED Requirements

### Requirement: Clone an agent without bindings
An admin SHALL be able to clone an existing agent under a new globally unique name. The clone SHALL copy the source agent's active version definition (system_prompt, allowed_tools, model_overrides, skills_dir, mcp_server_ids, memory_namespace) and SHALL NOT copy any user bindings or the default flag. The clone SHALL start in `status=enabled` and `provenance=adhoc`. （Channel 绑定不再存在——`channel_agents` 已 descope。）

#### Scenario: Clone copies definition, not bindings
- **WHEN** an admin clones "ops-bot" as "ops-bot-staging"
- **THEN** "ops-bot-staging" has the same system_prompt, allowed_tools, and model config as "ops-bot"'s active version
- **AND** "ops-bot-staging" has no `user_agents` rows and is not the default agent
- **AND** "ops-bot-staging" is `enabled`

#### Scenario: Clone with duplicate name rejected
- **WHEN** an admin clones "ops-bot" using a name that already exists and is not archived
- **THEN** the request is rejected (409) and nothing is persisted

#### Scenario: Clone is audited
- **WHEN** a clone succeeds
- **THEN** an `agent.clone` audit entry records the source and the new agent id
