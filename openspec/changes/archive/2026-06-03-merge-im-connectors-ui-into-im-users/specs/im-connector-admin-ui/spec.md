## MODIFIED Requirements

### Requirement: IM connector management section
The admin console SHALL present a section listing each IM platform connector with its platform, enabled flag, status, and masked credential summary. The section SHALL be visible to admins only.

This connector section SHALL live within the unified **IM** tab in the **Access** navigation group, shown on the same page as the IM-users list. The console SHALL NOT expose a separate top-level "IM Connectors" navigation entry. Opening the IM tab SHALL refresh both the IM-users list and the connector list.

#### Scenario: Admin sees connector list
- **WHEN** an admin opens the IM connectors section
- **THEN** each connector's platform, status, enabled flag, and masked credentials are shown

#### Scenario: Viewer cannot manage connectors
- **WHEN** a viewer is logged in
- **THEN** the connector management controls (add / enable / disable) are hidden

#### Scenario: Connectors and IM users share one tab
- **WHEN** an admin opens the IM tab from the Access group
- **THEN** both the IM-users block and the IM-connectors block are shown on the same page
- **AND** there is no separate "IM Connectors" navigation entry under any other group

#### Scenario: Opening the IM tab loads both blocks
- **WHEN** an admin switches to the IM tab
- **THEN** the console refreshes the IM-users list and the connector list
