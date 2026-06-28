# fleetent-apply-api

## ADDED Requirements

### Requirement: Agent apply API is retired
The platform SHALL NOT expose askit/apply-based agent mutation endpoints. Agent creation and update SHALL happen through the native admin agent APIs only, and the server SHALL NOT wire askit apply seams.

#### Scenario: Apply endpoint is unavailable
- **WHEN** a client calls `POST /admin/agents/apply`
- **THEN** the request is rejected because no apply endpoint is exposed

#### Scenario: Server uses native agent write path only
- **WHEN** the platform server handles an admin agent create or update
- **THEN** it writes through the native agent store seams
- **AND** no askit apply module is loaded
