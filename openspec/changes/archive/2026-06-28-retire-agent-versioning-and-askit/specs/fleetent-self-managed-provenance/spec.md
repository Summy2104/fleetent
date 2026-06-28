# fleetent-self-managed-provenance

## ADDED Requirements

### Requirement: Self-managed provenance flow is retired
The platform SHALL NOT distinguish agents by self-managed provenance states such as `spec_owned`, `db_only`, or managed/ad-hoc source badges. UI edits become the persisted current state directly, and there is no provenance-based promote/discard flow for agents.

#### Scenario: Agent UI shows no source badge
- **WHEN** an admin opens the agent console
- **THEN** the console shows no provenance/source badge for agents

#### Scenario: Agent edits do not enter a provenance reconciliation flow
- **WHEN** an admin saves an agent change in the UI
- **THEN** the change is persisted as the current state
- **AND** there is no agent-level promote, discard, or restore-on-deploy flow
