## ADDED Requirements

### Requirement: Per-user and global quotas
The system SHALL support token and call-count limits scoped to a single user or globally.

#### Scenario: Set per-user quota
- **WHEN** an admin sets a 10k-token quota for a user
- **THEN** the quota is recorded for that user

#### Scenario: Global quota applies to all
- **WHEN** a global quota is set
- **THEN** it applies across all users in addition to any per-user quota

### Requirement: Over-quota requests are rejected
When a user's (or the global) quota is exhausted, `/chat` SHALL return 429 and emit an over-quota event. Internal system calls (e.g. compression) MAY be exempt.

#### Scenario: Over-quota 429
- **WHEN** a user with an exhausted token quota calls `/chat`
- **THEN** the response is 429 with an over-quota message and an event is emitted

#### Scenario: Within quota proceeds
- **WHEN** a user under quota calls `/chat`
- **THEN** the request proceeds normally

#### Scenario: Internal calls exempt
- **WHEN** an internal system operation runs while the user is at quota
- **THEN** the internal call is not blocked by the user quota
