## MODIFIED Requirements

### Requirement: IM connector management section
The admin console SHALL present a section listing each IM platform connector with its platform, enabled flag, status, and masked credential summary. The section SHALL be visible to admins only.

This connector section SHALL live within the unified **Users** tab in the **Access** navigation group, attached under the User that owns each connector (`connectors.owner_id = user.id`). The console SHALL NOT expose a separate top-level "IM Connectors" navigation entry, and SHALL NOT expose a separate IM tab. Connector ownership SHALL be presented at the User level, not per IM identity. Opening the Users tab SHALL refresh both the user list and the connectors shown under their owning Users.

#### Scenario: Admin sees connector list
- **WHEN** an admin opens the unified Users tab
- **THEN** each connector's platform, status, enabled flag, and masked credentials are shown under its owning User

#### Scenario: Viewer cannot manage connectors
- **WHEN** a viewer is logged in
- **THEN** the connector management controls (add / enable / disable) are hidden

#### Scenario: Connectors attach to their owning User
- **WHEN** an admin opens the Users tab
- **THEN** each connector is shown under the User that owns it (`connectors.owner_id = user.id`)
- **AND** there is no separate "IM Connectors" navigation entry and no separate IM tab under any group

#### Scenario: Opening the Users tab refreshes connectors
- **WHEN** an admin switches to the Users tab
- **THEN** the console refreshes the user list and the connectors shown under their owning Users
