## ADDED Requirements

### Requirement: Agent console state storage

The agent operational state SHALL store `status` (`enabled` / `disabled` / `archived`, default `enabled`), `provenance` (`managed` / `adhoc`, default `adhoc`), and `drift` (integer boolean, default `0`). `status=archived` SHALL be consistent with the soft-delete marker (archive sets both; restore clears the soft-delete marker and sets `status=enabled`). These columns SHALL be provided via an Alembic migration that backfills existing rows (`status=enabled`, or `status=archived` where already soft-deleted; `provenance=adhoc`, `drift=0`). SQL SHALL use named parameters and go through the store boundary; no ORM.

> Implementation note: this state lives in a side table `agent_admin_state` (migration 015, modeled on `skill_admin_state`) keyed by agent name rather than ALTERing the `agents` table; this is the "console state" the agent-definition storage requirement defers archival/disable to.

#### Scenario: New columns added with defaults via migration
- **WHEN** the Alembic migration runs against an existing database
- **THEN** `agent_admin_state` gains `status` / `provenance` / `drift` columns; existing rows get `status=enabled` (or `archived` if already soft-deleted), `provenance=adhoc`, `drift=0`

#### Scenario: Archive keeps status and deleted_at consistent
- **WHEN** an agent is archived
- **THEN** `status` is `archived` AND `deleted_at` is set in the same transaction

#### Scenario: Restore clears soft delete
- **WHEN** an archived agent is restored within retention
- **THEN** `status` becomes `enabled` AND `deleted_at` is cleared

### Requirement: Routing honors agent status

Routing resolution SHALL reject new sessions for agents whose `status` is `disabled` or `archived`. A `disabled` agent SHALL yield a "该 Agent 已停用" rejection (reversible). An `archived` agent SHALL be treated as not routable (equivalent to not existing in the routable list).

> New constraint layered on the existing "soft-deleted agents not returned" behavior.

#### Scenario: Disabled agent not routable
- **WHEN** a message routes to an agent with `status=disabled`
- **THEN** the request is rejected with "该 Agent 已停用" and does not enter agent_loop

#### Scenario: Enabled agent routable
- **WHEN** a message routes to an agent with `status=enabled`
- **THEN** the request proceeds to agent_loop normally

#### Scenario: Archived agent absent from routable list
- **WHEN** the routable agent list is resolved
- **THEN** agents with `status=archived` are excluded
