## Why

IM functionality is split across two homes that share the same legacy SQLite DB but
live apart:

- **IM users** — `src/fleetent/im_user_store.py` (legacy top-level): `(owner_id,
  platform, platform_user_id)` → internal `User` mapping plus the per-identity
  allowlist (approve/block/rebind workbench).
- **IM connectors** — `src/fleetent/platform/im_gateway_management/` (5 files, 764
  lines): connector config + platform secrets, the connection registry/status,
  channel allowlist, the connector manager (async supervisor), and the `/admin/im`
  admin API.

Both already re-export `user_store.DB_PATH`, both own IM tables (`im_users`,
`im_connectors`, `im_channel_allowlist`), and callers (`im_gateway/*`, normalizer,
admin CLI, admin API) must reach into both to handle one IM message. Consolidating
into a single IM module removes that split: one module owns every IM table, the IM
public API, and the connector lifecycle.

This deliberately couples platform-connection config (bot tokens) with user identity
inside one module, which trades the current one-responsibility split for a single IM
seam. That tension is acknowledged and resolved by updating `module-boundaries` to
declare the unified IM module as the owner of all three tables.

## What Changes

- Consolidate the IM-users store and the four IM-connector implementation files
  (`im_connector_store`, `im_connector_config`, `im_connector_manager`,
  `im_channel_allowlist`) plus the `/admin/im` router into one IM module.
- The unified module owns `im_users`, `im_connectors`, `im_channel_allowlist` and
  exposes one documented public API surface (identity mapping, allowlist, connector
  config/registry/manager, admin router).
- Legacy import paths (`fleetent.im_user_store`, the four
  `fleetent.platform.im_gateway_management.*` modules) become compatibility shims
  that only re-export public names — no business logic.
- No schema change: the three tables keep their columns, keys, and the existing
  legacy-rebuild/`_init_db` behavior. Pure code-organization move; behavior preserved.
- All importers (src + tests) switch to the unified module's public API; tests are
  reorganized to the consolidated module without changing asserted behavior.

## Capabilities

### New Capabilities
- `im-module`: the consolidated IM module's public API surface and table ownership —
  identity mapping + allowlist + connector config/registry/manager + admin router
  exposed from one module, with documented internal vs public boundary.

### Modified Capabilities
- `module-boundaries`: declare the unified IM module as sole owner of `im_users`,
  `im_connectors`, and `im_channel_allowlist`; record the legacy import paths as
  compatibility shims pending cleanup.

## Impact

- **Code moved/merged**: `src/fleetent/im_user_store.py` +
  `src/fleetent/platform/im_gateway_management/{im_connector_store,im_connector_config,
  im_connector_manager,im_channel_allowlist,im_admin_api}.py` → unified IM module.
- **Importers updated** (~13 src, ~17 tests): `im_gateway/{slack,telegram,normalizer}.py`,
  `server.py`, `user_store.py`, `governance/blocklist.py`,
  `platform/user_management/user_admin_api.py`, `platform/admin_cli/{im,im_connectors}.py`,
  `static/admin.html` (paths unchanged for HTTP routes), and their test suites.
- **Public API**: new unified IM module API; old module paths kept as re-export shims.
- **Data/DB**: no Alembic migration — tables unchanged; existing `_init_db`/legacy
  rebuild paths move with the code.
- **No new dependencies**; no cloud services; SQLite-first, named params, no ORM.
