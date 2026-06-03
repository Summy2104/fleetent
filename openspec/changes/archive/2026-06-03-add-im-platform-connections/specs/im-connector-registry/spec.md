## ADDED Requirements

### Requirement: Create a connector for a not-yet-configured platform
The system SHALL allow an admin to create (initialize) a connector row for a platform that has no existing row, supplying its credential config in the same call. Creation SHALL be idempotent: creating for an existing platform SHALL update that platform's config rather than insert a duplicate (the `platform` UNIQUE constraint is preserved). Creation SHALL be admin-only.

#### Scenario: Create a brand-new platform connection
- **WHEN** an admin POSTs a `whatsapp` connector with a credential config and no `whatsapp` row exists
- **THEN** an `im_connectors` row for `whatsapp` is created with that config and the masked connector is returned

#### Scenario: Create for an existing platform updates config
- **WHEN** an admin POSTs a `slack` connector config while a `slack` row already exists
- **THEN** the existing row's config is updated (no duplicate row) and the UNIQUE(platform) constraint is not violated

#### Scenario: Non-admin cannot create a connector
- **WHEN** a viewer attempts to create a connector
- **THEN** the request is rejected with 403 and no row is written
