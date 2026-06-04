## Why

The admin console splits identity across two places: a **Users** tab (internal users) and an **IM** tab (IM identities + connectors). But every IM identity is already bound to exactly one internal User (`im_users.user_id → users.id`), and every connector is owned by a User (`connectors.owner_id → users.id`). Showing these on separate axes hides the real relationship and forces admins to cross-reference. A single User-centric view — each User row, with its IM identities and owned connectors foldable underneath — matches the data model and is easier to operate.

## What Changes

- **BREAKING (UI nav):** Merge the **Users** and **IM** tabs into a single **Users** tab under the Access group. Remove the standalone IM tab (and with it the platform-grouped connector+users view introduced by `merge-im-connectors-ui-into-im-users`).
- Users list becomes the single identity axis: one row per internal User.
  - A User that has bound IM identities (`im_users.user_id = user.id`) shows an expand/collapse control; expanding lists each IM identity (platform, platform_user_id, allowed state) with Bind / Block / Restore actions.
  - A User with no IM identities shows no expander.
  - Connectors owned by a User (`connectors.owner_id = user.id`) are shown under that User (with status / enabled / masked credentials / enable-disable, plus Add connection).
- **Owner is presented at the User level, not per IM identity.** The unified view keys everything off the owning/bound User; the per-`im_users` `owner_id` column is dropped from display (no schema change — `users` has no `owner_id`; the User itself is the owner anchor for its connectors).
- **Source filter** distinguishes auto-created IM-origin Users (name like `slack:U123`) from human/API Users. A source badge marks each row; a filter toggle controls which are shown (default: all).
- Two block semantics are made explicit in the UI: `users.status` (whole-User disable) vs `im_users.allowed` (single IM identity block) — rendered as distinct controls/labels so they are not confused.

Behavior-preserving for backend: no route/API/schema change. All existing operations (user block/disable/delete/role, IM bind/block/restore, connector add/enable/disable, credential masking) keep their semantics; only the console's presentation axis changes.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `web-user-management`: the "User list and lifecycle" requirement gains the User-centric unified view — foldable IM identities per User, connectors grouped under their owning User, and a source filter distinguishing IM-origin from human/API Users.
- `im-connector-admin-ui`: the "IM connector management section" requirement moves from a standalone IM tab to the unified Users tab, attached under the owning User; the separate IM tab / platform-grouped block is removed.

## Impact

- **Frontend only:** `src/fleetent/static/admin.html` — nav (remove IM tab, repoint Access group), Users section markup, `loadUsers`/`renderUsers` (fold IM identities + connectors per User), source filter control, removal of the platform-grouped `loadIm`/`#im-groups` block, `TAB_GROUP`/`LOADERS` wiring.
- **Backend:** unchanged — reuses `/admin/users`, `/admin/im-users`, `/admin/im/connectors` and the IM package public API.
- **Tests:** `tests/integration/test_admin_console_ui.py`, `tests/integration/test_im_admin_api.py` (UI-marker assertions updated to the unified Users axis).
