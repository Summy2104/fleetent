# agent-lifecycle-toggle

## MODIFIED Requirements

### Requirement: Binding protection before archive
Archiving (soft delete) an agent SHALL be blocked while it is still referenced by any of: a bound user, an IM group binding, an MCP server binding, a knowledge-base binding, an external-service grant, a node placement (pinned), or being set as the default agent. The block response SHALL enumerate the occupying references by type. Archive SHALL only proceed when no references of any type remain.（Channel 绑定已 descope，不再纳入阻挡判定。）

#### Scenario: Archive blocked while bound to a user or default
- **WHEN** an admin requests archive of "ops-bot" which is still bound to a user (or is the default agent)
- **THEN** the request is rejected (409) and the response lists the occupying references (including user ids and default flag)
- **AND** the agent's `status` and `deleted_at` are unchanged

#### Scenario: Archive blocked while bound to non-user resources
- **WHEN** an admin requests archive of "ops-bot" which has no user binding and is not default, but still has an MCP / KB / skill-or-service grant / IM group binding or an active node placement
- **THEN** the request is rejected (409) and the response lists the occupying reference types
- **AND** the agent's `status` and `deleted_at` are unchanged

#### Scenario: Archive proceeds after all references removed
- **WHEN** "ops-bot" has no remaining references of any tracked type (no user/IM/MCP/KB/grant binding, no placement) and is not default, and an admin confirms archive
- **THEN** the agent's `status` becomes `archived` and `deleted_at` is set in the same transaction
- **AND** the agent is removed from the routable list and an `agent.archive` audit entry exists
