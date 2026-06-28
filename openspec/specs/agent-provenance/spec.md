# agent-provenance Specification

## Purpose
TBD - updated by archiving change retire-agent-versioning-and-askit. Refine after archive if needed.
## Requirements
### Requirement: Agent provenance and drift badges are retired
The system SHALL NOT store or expose agent-level `provenance` or `drift` state. Agents are authored only as current-state console definitions, and the admin surfaces SHALL NOT render managed/adhoc provenance badges or agent-level drift badges.

#### Scenario: Listing an agent does not expose provenance
- **WHEN** the admin console or admin API reads an agent definition
- **THEN** the payload contains no agent-level `provenance` or `drift` field
- **AND** the UI renders no provenance or drift badge

#### Scenario: Editing an agent does not create agent-level drift
- **WHEN** an admin edits an agent in the console
- **THEN** the edited values become the current state directly
- **AND** no agent-level drift marker is stored or shown
