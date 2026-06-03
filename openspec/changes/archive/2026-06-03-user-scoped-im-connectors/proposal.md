# Make IM connectors user-scoped (multi-tenant)

## Why

Today IM connectors are a deployment-wide singleton: `im_connectors` is keyed by
`platform UNIQUE`, the connector manager runs at most one adapter per platform, and
inbound routing resolves agent/session/allowlist with no notion of which owner the
traffic belongs to. A single self-hosted deployment therefore cannot host more than
one Slack/Telegram/WhatsApp bot, and every platform user is funneled into one shared
identity/allowlist space.

We want each fleetent platform user (owner) to register their own connector
configuration (their own bot token) per platform, run concurrently with other owners,
and have their inbound traffic isolated end to end (identity mapping, allowlist,
agent binding, sessions).

## What Changes

- **Connector registry** re-keyed from `platform` to `(owner_id, platform)`; multiple
  rows per platform coexist, one per owner.
- **Connector config resolution** scoped by owner. `.env` fallback applies only to the
  built-in **admin owner**; other owners must configure explicitly.
- **Connector manager** runs one adapter task per `(owner_id, platform)` with that
  owner's resolved credentials; status/heartbeat reported per owner.
- **Inbound routing** carries `owner_id` from the receiving adapter through
  `NormalizedMessage` into agent resolution, IM-user identity, allowlist, and session
  namespacing, so two owners never share state.
- **IM user mapping + allowlist** re-keyed to include `owner_id`
  (`(owner_id, platform, platform_user_id)`); same platform user under different owners
  is distinct.
- **Admin API** scopes list/read/write to the caller's owner; an **admin/superuser sees
  and manages all owners'** connectors and allowlist entries.
- **Admin UI** "IM Connectors" tab shows the caller's connectors (admin: all, with owner
  column); create/edit attaches to the caller's owner.
- **Migration**: existing global rows are reassigned to the admin owner; existing IM
  users / allowlist entries likewise. Backward compatible for the current single-tenant
  deployment.

## Impact

- Affected specs: `im-connector-registry`, `im-connector-config`, `im-connector-admin-ui`,
  `im-user-mapping`, `im-user-allowlist`, `im-channel-allowlist`, `im-gateway` (modified);
  new behavior captured under capability `user-scoped-im-connectors`.
- Affected code: `im_connector_store`, `im_connector_config`, `im_connector_manager`,
  `im_admin_api`, `im_channel_allowlist`, `im_user_store`, `im_gateway/normalizer.py`,
  `im_gateway/slack.py`, `im_gateway/telegram.py`, WhatsApp webhook routing,
  `static/admin.html`, Alembic migration, related tests.
- No new third-party dependency. SQLite-first, named SQL params, schema via Alembic.
