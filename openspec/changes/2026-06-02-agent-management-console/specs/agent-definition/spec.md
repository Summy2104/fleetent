## MODIFIED Requirements

### Requirement: Agent definition storage
> Extends the `agents` schema from `2026-05-29-multi-agent-management` (which added `active_version_id` / `deleted_at`). This change adds operational columns; existing columns are unchanged.

The `agents` table SHALL additionally store `status` (`enabled` / `disabled` / `archived`, default `enabled`), `provenance` (`managed` / `adhoc`, default `adhoc`), and `drift` (integer boolean, default `0`). `status=archived` SHALL be consistent with `deleted_at IS NOT NULL` (archive sets both; restore clears `deleted_at` and sets `status=enabled`). These columns SHALL be added via an Alembic migration that backfills existing rows (`status=enabled`, or `status=archived` where `deleted_at` is already set; `provenance=adhoc`, `drift=0`). SQL SHALL use named parameters and go through the `agent_store` boundary; no ORM.

#### Scenario: New columns added with defaults via migration
- **WHEN** the Alembic migration runs against an existing database
- **THEN** `agents` gains `status` / `provenance` / `drift` columns; existing rows get `status=enabled` (or `archived` if already soft-deleted), `provenance=adhoc`, `drift=0`

#### Scenario: Archive keeps status and deleted_at consistent
- **WHEN** an agent is archived
- **THEN** `status` is `archived` AND `deleted_at` is set in the same transaction

#### Scenario: Restore clears soft delete
- **WHEN** an archived agent is restored within retention
- **THEN** `status` becomes `enabled` AND `deleted_at` is cleared

### Requirement: Routing honors agent status
> New constraint layered on the existing "soft-deleted agents not returned" behavior.

Routing resolution SHALL reject new sessions for agents whose `status` is `disabled` or `archived`. A `disabled` agent SHALL yield a "该 Agent 已停用" rejection (reversible). An `archived` agent SHALL be treated as not routable (equivalent to not existing in the routable list).

#### Scenario: Disabled agent not routable
- **WHEN** a message routes to an agent with `status=disabled`
- **THEN** the request is rejected with "该 Agent 已停用" and does not enter agent_loop

#### Scenario: Enabled agent routable
- **WHEN** a message routes to an agent with `status=enabled`
- **THEN** the request proceeds to agent_loop normally

#### Scenario: Archived agent absent from routable list
- **WHEN** the routable agent list is resolved
- **THEN** agents with `status=archived` are excluded
