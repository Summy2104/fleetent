# agent-lifecycle-toggle Delta

## MODIFIED Requirements

### Requirement: Enable / disable toggle preserves definition and bindings
An admin SHALL be able to disable an enabled agent and re-enable a disabled agent. Disabling SHALL keep the agent's definition, all versions, and all user bindings intact, but SHALL stop the agent from accepting new sessions. Re-enabling SHALL immediately restore service. Both actions SHALL be audited. （Channel 绑定不再存在——`channel_agents` 已 descope。）

#### Scenario: Disabled agent rejects a new session
- **WHEN** agent "ops-bot" has been disabled by an admin and a message routes to "ops-bot"
- **THEN** the request is rejected with the message "该 Agent 已停用" and does not enter agent_loop
- **AND** an `agent.disable` audit entry exists with `target_id` = the agent id

#### Scenario: Re-enabling restores service
- **WHEN** an admin re-enables a previously disabled "ops-bot" and the same message routes to it
- **THEN** the request is accepted and enters agent_loop normally
- **AND** an `agent.enable` audit entry exists

#### Scenario: Disable keeps bindings
- **WHEN** "ops-bot" has user bindings and is then disabled
- **THEN** the `user_agents` rows for "ops-bot" are unchanged and the agent definition/versions are preserved

### Requirement: Binding protection before archive
Archiving (soft delete) an agent SHALL be blocked while it is still bound to any user, or set as the default agent. The block response SHALL list the occupying users and whether it is the default. Archive SHALL only proceed when no references remain. （Channel 绑定已 descope，不再纳入阻挡判定。）

#### Scenario: Archive blocked while bound
- **WHEN** an admin requests archive of "ops-bot" which is still bound to a user (or is the default agent)
- **THEN** the request is rejected (409) and the response lists the occupying user ids and default flag
- **AND** the agent's `status` and `deleted_at` are unchanged

#### Scenario: Archive proceeds after unbinding
- **WHEN** "ops-bot" has no remaining user bindings and is not default, and an admin confirms archive
- **THEN** the agent's `status` becomes `archived` and `deleted_at` is set in the same transaction
- **AND** the agent is removed from the routable list and an `agent.archive` audit entry exists
