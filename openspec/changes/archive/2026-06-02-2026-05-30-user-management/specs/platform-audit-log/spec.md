## ADDED Requirements

### Requirement: All admin write operations are audited
Every platform management write (create/delete user, rotate/revoke key, block/restore IM user, change role, change quota) SHALL write an audit entry capturing who, when, on what resource, and what action.

#### Scenario: Rotate key audited
- **WHEN** admin `admin1` rotates user Alice's key
- **THEN** an audit row is written with actor `admin1`, action `rotate_key`, target = the key/user, and a timestamp

### Requirement: Audit log is searchable and exportable
The system SHALL allow searching audit entries by actor, action, target, and time range, and exporting the results.

#### Scenario: Search by action
- **WHEN** an admin filters the audit log by `action=rotate_key`
- **THEN** matching entries are returned, including actor, timestamp, and target

#### Scenario: Export
- **WHEN** an admin exports a filtered audit view
- **THEN** the entries are exported (e.g. CSV)

### Requirement: High-risk operations require second confirmation
Delete-user, revoke-key, and batch-block SHALL require a second confirmation (2FA) before executing, and the confirmation outcome SHALL be audited.

#### Scenario: High-risk needs confirmation
- **WHEN** an admin triggers a delete-user without passing the second confirmation
- **THEN** the business change is not applied; once confirmed it executes and is audited
