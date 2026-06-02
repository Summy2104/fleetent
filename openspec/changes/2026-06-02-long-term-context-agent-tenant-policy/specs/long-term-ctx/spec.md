## ADDED Requirements

### Requirement: Agent tenant context policy design
long-term-ctx SHALL support tenant default and agent override policies for User Memory, Shared Memory, and Knowledge Base context sources.

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
- **WHEN** Shared Memory has no enabled policy with scope information
- **THEN** long-term-ctx does not query Shared Memory

#### Scenario: Policy budget controls source selection
- **WHEN** policies define per-source top-k and token budgets
- **THEN** long-term-ctx applies those limits before rendering injectable context
