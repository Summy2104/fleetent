## MODIFIED Requirements

### Requirement: platform 只读 agent 侧库

platform SHALL read agent-side physical databases through read-only connections only — never writing, never migrating. Discovery uses the management DB registry; each agent's DB is opened via tenant-first router `agent_scope(tenant_id, agent_name).open_*_ro()`.

#### Scenario: Session projection opens tenant-first state DB read-only
- **WHEN** platform aggregates sessions for tenant `acme` agent `support`
- **THEN** it opens `tenants/acme/agents/support/data/agent_state.db` read-only through router
- **AND** it does not migrate or write that DB

#### Scenario: Missing agent DB is skipped
- **WHEN** an agent has never booted and its tenant-first DB file does not exist
- **THEN** platform projection skips it without creating the DB

#### Scenario: Projection does not use old data layout
- **WHEN** platform reads traces, approvals, sessions, or agent memory
- **THEN** it does not look under `data/<tenant>/<agent>/`
