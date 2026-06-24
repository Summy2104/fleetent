## ADDED Requirements

### Requirement: Managed skill file deployment is node-owned

In managed mode, platform SHALL project skill visibility decisions into agent config and desired-state, but node SHALL be the component that writes skill files into the agent home. Agent runtime SHALL read only the tenant-aware local skill copy under its home.

#### Scenario: Allowed skills remain config-driven
- **WHEN** an agent has explicit skill bindings
- **THEN** generated agent config contains the corresponding `allowed_skills`
- **AND** runtime uses that config to build its catalog

#### Scenario: Node writes the local skill copy
- **WHEN** desired-state includes skill `foo` for tenant `acme` agent `bot`
- **THEN** node writes files under `tenants/acme/agents/bot/skills/foo/`
- **AND** platform does not write those files directly in managed mode

#### Scenario: Runtime reads local copy only
- **WHEN** the agent runtime loads skill `foo`
- **THEN** it reads from its own home `skills/foo/`
- **AND** it does not read the public skill pool or platform management DB
