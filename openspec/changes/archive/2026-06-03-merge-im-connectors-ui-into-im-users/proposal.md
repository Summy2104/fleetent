## Why

The backend IM modules were already unified (archived `merge-im-connectors-into-im-users`), but the admin console still splits IM management across two tabs: "IM Users" (Access group) and "IM Connectors" (Models & Connectors group). Operators manage one logical IM domain from two distant nav entries. Consolidating the user-visible layer matches the unified module and reduces navigation friction.

## What Changes

- Merge the "IM Connectors" tab into the "IM Users" tab. A single **IM** tab under the **Access** group shows both the connectors block and the IM-users block on one page.
- **BREAKING (UI nav only)**: remove the standalone `IM Connectors` nav item from the "Models & Connectors" group and remove the separate `#tab-connectors` section. The connectors content (table, add-connection modal, credential fields, enable/disable/delete) moves into the IM tab.
- Wire the IM tab loader to refresh both blocks (IM users + connectors) when the tab opens.
- No backend changes: `/admin/im/*`, `/admin/users`, connector create/enable/disable/delete, credential masking, and user block/restore/bind keep identical routes and semantics.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `im-connector-admin-ui`: the connector management section is relocated into the unified IM tab (Access group) alongside IM Users, with no separate top-level nav entry; all connector management behavior is preserved.

## Impact

- `src/fleetent/static/admin.html`: nav markup (remove connectors nav item), section markup (fold `#tab-connectors` content into `#tab-im`), JS (`TAB_GROUP`, `LOADERS.im`/`LOADERS.connectors`, `switchTab`); `loadConn`, `openConnModal`, `conn-body`, `conn-create-bar` retained but relocated.
- `tests/integration/test_admin_console_ui.py`: marker assertions that expect a separate `connectors` tab/nav entry are updated to assert the consolidated layout.
- No API, schema, or dependency changes.
