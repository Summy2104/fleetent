# Design: user-scoped IM connectors

## Context

Single-tenant today. `im_connectors.platform` is `UNIQUE`; manager keys tasks by
platform; `normalizer.route()` resolves agent/allowlist/identity without an owner.
Goal: per-owner connectors running concurrently with isolated inbound state, while the
existing single-bot deployment keeps working after migration.

"Owner" = a `users.id` (the fleetent platform user who owns a bot config). The built-in
admin user is the default owner that inherits today's global config.

## Decisions

### D1 — Composite key `(owner_id, platform)` everywhere
`im_connectors` PK becomes `(owner_id, platform)` (drop `platform UNIQUE`, add
`owner_id TEXT NOT NULL` FK→`users.id`). Store functions take `owner_id` as first arg.
`im_users` and the allowlist tables gain `owner_id`, re-keyed to
`(owner_id, platform, platform_user_id)`.

Rationale: the cleanest isolation boundary; admin "see all" is just an unfiltered query.

### D2 — Owner resolution at the edges
- **Outbound/admin**: `owner_id` = authenticated caller's user id. Admin/superuser may
  pass an explicit `owner_id` (query param / path) to act on any owner; non-admin
  callers are forced to their own id (ignore/deny mismatched `owner_id`).
- **Inbound (Slack/Telegram)**: each adapter task is started per `(owner_id, platform)`,
  so `owner_id` is captured in the task closure and stamped onto `NormalizedMessage`.
- **Inbound (WhatsApp webhook)**: a single HTTP endpoint receives all traffic; resolve
  `owner_id` by looking up the destination `phone_number_id` in connector configs
  (unique per owner). Reject if unmapped.

### D3 — Config resolution + `.env` fallback admin-only
`im_connector_config.resolve(owner_id, platform)` reads that owner's row. `.env`
fallback (`_env_fallback`) applies **only when `owner_id == admin_owner_id`**, preserving
current behavior for the migrated admin bot. Other owners with no DB config resolve empty
→ `unconfigured`. `seed_from_env()` seeds the admin owner only.

### D4 — Manager runs one task per (owner, platform)
`ConnectorManager` keys `_tasks` by `(owner_id, platform)` tuple. `start/stop/reload`
take `owner_id`. `start_all_enabled()` iterates all enabled rows across owners. Status
APIs (`report_status`, `heartbeat`) take `owner_id`. Adapter factories receive the
resolved config plus `owner_id` so the adapter can stamp inbound messages.

### D5 — Inbound routing threads owner_id
`NormalizedMessage` gains `owner_id`. `normalizer.route()` uses it for:
- `im_user_store.get_or_create(owner_id, platform, platform_user_id)`
- channel + user allowlist checks scoped by owner
- agent resolution scoped by owner (channel binding / user binding / **owner's** default
  agent before global default)
- **session id namespacing**: prefix session id with `owner_id` so two owners' same
  platform/channel/user never collide.

### D6 — Admin scoping
`im_admin_api` derives `owner_id` from auth. List/read/write filter by owner. A request
from an admin role with `?owner_id=` (or `all`) returns/acts across owners; the response
includes `owner_id` per row so the UI can show an owner column. Destructive/write still
admin-gated as today; secret values stay masked and never prefilled.

### D7 — Migration via idempotent `_init_db` rebuild (not Alembic)
The IM/user subsystem tables (`users`, `im_connectors`, `im_users`,
`im_channel_allowlist`) are lazily bootstrapped by each store's `_init_db()`, not by
Alembic (precedent: the `allowed` column was added via an idempotent `_init_db` ALTER).
We follow that precedent rather than introducing an Alembic migration that would diverge
from the subsystem's real schema source.

Each affected store's `_init_db()`:
1. CREATE the owner-keyed table for fresh databases.
2. Detect the pre-change shape (no `owner_id` column) and **rebuild in place**: create the
   new owner-keyed table, copy rows backfilling `owner_id` = admin owner id, drop old,
   rename. SQLite can't ALTER a UNIQUE/PK, so a table rebuild is required.

Admin owner id is resolved via `user_store.get_builtin_admin()` at patch time; if no admin
exists yet, rows are backfilled with sentinel `__system__`, reassigned to the admin owner
on next `seed_from_env()`. Idempotent and data-preserving.

### D8 — TDD via store/manager/routing units + UI markers
Each layer gets failing tests first: store composite-key CRUD + owner filtering;
config resolution owner gating; manager per-owner task lifecycle; normalizer owner
threading + session namespacing; admin api owner scoping + admin-see-all; UI marker for
owner column + create-attaches-owner. Migration covered by an integration test that
seeds a pre-migration shaped row and asserts post-migration shape + admin-owner backfill.

## Risks / Trade-offs

- **Session id change** could orphan in-flight single-tenant sessions. Mitigate: admin
  owner keeps the un-prefixed form (or prefix is `adminOwnerId`), so migrated sessions
  resolve. Documented in migration.
- **WhatsApp owner-by-phone_number_id** requires unique phone ids across owners; enforce
  at config write (reject duplicate phone_number_id).
- Large surface; staged so each store/manager/routing change lands behind passing tests.

## Migration / Rollback

Rollback = revert the migration (drop owner_id, restore platform-unique) and revert code.
Since admin-owner backfill is lossless, downgrade collapses back to single-tenant with
the admin owner's rows retained as the global rows.
