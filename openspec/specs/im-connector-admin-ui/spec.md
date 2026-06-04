# im-connector-admin-ui Specification

## Purpose
TBD - created by syncing change add-im-platform-connections. Update Purpose after archive.
## Requirements
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

### Requirement: Add-connection modal with platform dropdown
The admin console SHALL provide an "Add connection" modal whose platform field is a dropdown containing `telegram`, `slack`, and `whatsapp`. Submitting the modal SHALL create the connector via the admin API.

#### Scenario: Open add-connection modal
- **WHEN** an admin clicks "Add connection"
- **THEN** a modal opens with a platform dropdown listing telegram, slack, and whatsapp

#### Scenario: Submit creates the connector
- **WHEN** an admin selects a platform, fills its credential fields, and submits
- **THEN** the console POSTs the credentials to the connector create endpoint and refreshes the list

### Requirement: Dynamic per-platform credential fields
The modal SHALL render credential input fields that match the selected platform's credential schema, and SHALL re-render the fields when the selected platform changes.

#### Scenario: Telegram shows one field
- **WHEN** `telegram` is selected
- **THEN** only a `bot_token` field is shown

#### Scenario: Slack shows three fields
- **WHEN** `slack` is selected
- **THEN** `bot_token`, `signing_secret`, and `app_token` fields are shown

#### Scenario: WhatsApp shows four fields
- **WHEN** `whatsapp` is selected
- **THEN** `phone_number_id`, `access_token`, `verify_token`, and `business_account_id` fields are shown

#### Scenario: Switching platform re-renders fields
- **WHEN** an admin switches the dropdown from `telegram` to `whatsapp`
- **THEN** the single telegram field is replaced by the four whatsapp fields

### Requirement: Enable and disable a connector from the console
The admin console SHALL let an admin enable or disable a listed connector, calling the corresponding admin API endpoint.

#### Scenario: Enable a configured connector
- **WHEN** an admin clicks enable on a configured connector
- **THEN** the console calls the enable endpoint and the row reflects enabled=true

#### Scenario: Disable a connector
- **WHEN** an admin clicks disable on an enabled connector
- **THEN** the console calls the disable endpoint and the row reflects enabled=false
