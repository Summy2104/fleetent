## ADDED Requirements

### Requirement: Enable / disable toggle preserves definition and bindings
An admin SHALL be able to disable an enabled agent and re-enable a disabled agent. Disabling SHALL keep the agent's definition, all versions, and all user/channel bindings intact, but SHALL stop the agent from accepting new sessions. Re-enabling SHALL immediately restore routing. Both actions SHALL be audited.

#### Scenario: Disabled agent rejects a new session
- **WHEN** agent "ops-bot" has been disabled by an admin and a message routes to "ops-bot"
- **THEN** the request is rejected with the message "该 Agent 已停用" and does not enter agent_loop
- **AND** an `agent.disable` audit entry exists with `target_id` = the agent id

#### Scenario: Re-enabling restores service
- **WHEN** an admin re-enables a previously disabled "ops-bot" and the same message routes to it
- **THEN** the request is accepted and enters agent_loop normally
- **AND** an `agent.enable` audit entry exists

#### Scenario: Disable keeps bindings
- **WHEN** "ops-bot" is bound to channel C1 and is then disabled
- **THEN** the `channel_agents` and `user_agents` rows for "ops-bot" are unchanged and the agent definition/versions are preserved

### Requirement: Binding protection before archive
Archiving (soft delete) an agent SHALL be blocked while it is still bound to any user or channel, or set as the default agent. The block response SHALL list the occupying users, channels, and whether it is the default. Archive SHALL only proceed when no references remain.

#### Scenario: Archive blocked while bound
- **WHEN** an admin requests archive of "ops-bot" which is still bound to a channel (or is the default agent)
- **THEN** the request is rejected (409) and the response lists the occupying user ids, (platform, channel_id) pairs, and default flag
- **AND** the agent's `status` and `deleted_at` are unchanged

#### Scenario: Archive proceeds after unbinding
- **WHEN** "ops-bot" has no remaining user/channel bindings and is not default, and an admin confirms archive
- **THEN** the agent's `status` becomes `archived` and `deleted_at` is set in the same transaction
- **AND** the agent is removed from the routable list and an `agent.archive` audit entry exists

### Requirement: Archive requires confirmation and is reversible within retention
Archiving SHALL require a second confirmation (high-risk action). An archived agent SHALL be restorable to `enabled` within the retention period; restore SHALL clear `deleted_at`. Both archive and restore SHALL be audited. Hard cleanup beyond retention SHALL be operator-only and not exposed via CLI.

#### Scenario: Archive without confirmation is refused
- **WHEN** an archive request arrives without the required confirmation flag
- **THEN** the agent is not archived and no state change is persisted

#### Scenario: Restore within retention re-enables
- **WHEN** an admin restores an archived "ops-bot" that is within the retention period
- **THEN** the agent's `status` becomes `enabled`, `deleted_at` is cleared, and it is routable again
- **AND** an `agent.restore` audit entry exists

#### Scenario: Archived agent history remains queryable
- **WHEN** an agent has been archived
- **THEN** its historical traces remain queryable for audit even though it is not routable

### Requirement: State machine transitions
The agent `status` field SHALL only transition along `enabled ↔ disabled`, `enabled → archived`, `disabled → archived`, and `archived → enabled` (restore). Other transitions SHALL be rejected.

#### Scenario: Enable a disabled agent
- **WHEN** an agent is `disabled` and `enable` is requested
- **THEN** `status` becomes `enabled`

#### Scenario: Archive from disabled
- **WHEN** an agent is `disabled`, has no references, and archive is confirmed
- **THEN** `status` becomes `archived`

#### Scenario: Invalid transition rejected
- **WHEN** a transition not in the allowed set is requested (e.g. archive without passing binding protection)
- **THEN** the request is rejected and `status` is unchanged
