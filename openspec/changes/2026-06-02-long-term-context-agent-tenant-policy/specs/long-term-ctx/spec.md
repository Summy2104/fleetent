## ADDED Requirements

### Requirement: Agent tenant context policy design
long-term-ctx SHALL support tenant default and agent override policies for User Memory, Shared Memory, and Knowledge Base context sources.

#### Scenario: Agent ownership is required for Shared Memory policy
- **WHEN** policy resolution runs for an agent
- **THEN** it uses the agent boundary's `tenant_id` and optional `team_id`
- **AND** it does not infer team ownership from agent name, channel, user, or KB binding

#### Scenario: Default policy preserves current behavior
- **WHEN** no explicit context policy exists
- **THEN** User Memory and Knowledge Base behavior remains unchanged
- **AND** Shared Memory is not queried

#### Scenario: Tenant policy can enable or disable sources
- **WHEN** a tenant policy disables a source
- **THEN** long-term-ctx does not query that source
- **AND** budget decisions record that the source was disabled by policy

#### Scenario: Agent policy overrides tenant policy
- **WHEN** tenant and agent policies both define the same source
- **THEN** the agent policy takes precedence for that agent

#### Scenario: Shared Memory requires explicit policy
- **WHEN** Shared Memory has no enabled tenant/team policy
- **THEN** long-term-ctx does not query Shared Memory

#### Scenario: Tenant Shared Memory uses agent tenant
- **WHEN** tenant Shared Memory is enabled for an agent whose `tenant_id` is `acme`
- **THEN** long-term-ctx queries Shared Memory scope `tenant/acme`

#### Scenario: Team Shared Memory uses agent team
- **WHEN** team Shared Memory is enabled for an agent whose `team_id` is `support`
- **THEN** long-term-ctx queries Shared Memory scope `team/support`

#### Scenario: Cross-scope grants are not supported
- **WHEN** an agent belongs to tenant `acme` and team `support`
- **THEN** policy cannot grant Shared Memory from another tenant or another team

#### Scenario: Policy budget controls source selection
- **WHEN** policies define per-source top-k and token budgets
- **THEN** long-term-ctx applies those limits before rendering injectable context
