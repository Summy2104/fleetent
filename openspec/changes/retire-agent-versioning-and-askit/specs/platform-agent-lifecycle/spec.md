# platform-agent-lifecycle

## MODIFIED Requirements

### Requirement: Create/update materializes a runnable agent home

When the platform creates or updates a managed agent, it SHALL update the management database and make a new desired-state payload available to the owning node. Update SHALL be an in-place write to the agent's current-state row in the `agents` table (the single source of truth); it SHALL NOT mint a new agent version and SHALL NOT change any version pointer. Platform SHALL NOT write the managed agent's real home directly. The owning node SHALL materialize the runnable home under `FLEETENT_HOME/tenants/<tenant>/agents/<agent>/`.

#### Scenario: Create exposes desired state
- **WHEN** an admin creates managed agent `support` on the platform
- **THEN** platform persists the authored definition in management DB
- **AND** `GET /nodes/{node-id}/desired-state` includes `support` for its placement
- **AND** platform does not write `tenants/<tenant>/agents/support/agent.yaml` itself

#### Scenario: Update changes desired state
- **WHEN** an admin edits `support`'s definition
- **THEN** platform updates the management DB source of truth
- **AND** the next desired-state response contains the updated agent config
- **AND** the owning node is responsible for rewriting the home and restarting if needed

#### Scenario: Update writes current state in place without versioning
- **WHEN** an admin edits `support`'s runtime config (system_prompt / allowed_tools / model_overrides / memory_namespace / skills_dir) or caps fields
- **THEN** platform UPDATEs the `support` row in `agents` in place
- **AND** no agent version is created and no version pointer is changed
- **AND** the resulting desired-state config is materialized from the `agents` current-state row
