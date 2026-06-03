## 1. Schema migration (idempotent `_init_db` rebuild)

- [x] 1.1 Write failing integration test: a pre-change shaped `im_connectors`/`im_users`/`im_channel_allowlist` (global, no owner_id) rebuilds in place to owner-keyed with owner_id backfilled to the built-in admin owner; rows preserved; two owners can hold same platform after rebuild (tests/integration/test_user_scoped_im_migration.py)
- [x] 1.2 Update each store `_init_db()`: owner-keyed CREATE for fresh + detect-and-rebuild old shape backfilling admin owner (sentinel `__system__` if no admin); run pytest → green

## 2. Connector store (owner-keyed)

- [x] 2.1 Write failing unit test: `im_connector_store` CRUD keyed by `(owner_id, platform)`; two owners coexist; `list_connectors(owner_id)` filters; `list_connectors(owner_id=None)` returns all for admin (tests/unit/test_im_connector_store.py)
- [x] 2.2 Re-key store functions on `(owner_id, platform)` using named SQL params; run pytest → green

## 3. Config resolution (owner scope + admin-only env)

- [x] 3.1 Write failing unit test: `resolve(owner_id, platform)` reads owner row; `.env` fallback only for admin owner; non-admin → empty/unconfigured; `seed_from_env` seeds admin owner only (tests/unit/test_im_connector_config.py)
- [x] 3.2 Thread owner_id through resolve/resolve_masked/set_config/seed_from_env; gate env fallback on admin owner; run pytest → green

## 4. Connector manager (per-owner tasks)

- [x] 4.1 Write failing unit test: manager keys tasks by `(owner_id, platform)`; concurrent owners; start/stop/reload per owner; `start_all_enabled` spans owners; status reported per owner (tests/unit/test_im_connector_manager.py)
- [x] 4.2 Re-key `_tasks`, thread owner_id through start/stop/reload/start_all_enabled; pass owner_id to adapter factory; run pytest → green

## 5. Inbound routing (owner threading + session namespacing)

- [x] 5.1 Write failing unit test: `NormalizedMessage.owner_id` threaded; `route()` uses owner-scoped identity/allowlist/agent resolution; session id namespaced by owner; same platform user under two owners → distinct identity + session (tests/unit/test_normalizer.py additions)
- [x] 5.2 Add owner_id to NormalizedMessage; scope `im_user_store.get_or_create`, allowlist checks, agent resolution, and session id by owner; run pytest → green

## 6. IM identity + allowlist (owner-keyed)

- [x] 6.1 Write failing unit test: `im_user_store` get_or_create + allowlist keyed by `(owner_id, platform, platform_user_id)`; allowlist isolated per owner; `im_channel_allowlist` owner-scoped (tests/unit/test_im_user_store.py, test_im_channel_allowlist.py)
- [x] 6.2 Add owner_id to identity/allowlist store functions + channel allowlist; run pytest → green

## 7. Adapters carry owner_id

- [x] 7.1 Write failing unit test: Slack + Telegram adapters stamp owner_id from their task context onto NormalizedMessage (tests/unit/test_im_adapter_owner.py). NOTE: no inbound WhatsApp adapter exists (whatsapp is config-schema only), so phone_number_id→owner webhook resolution has no code path and is deferred.
- [x] 7.2 Pass owner_id into adapter factories (run/create_app/_heartbeat); stamp on outbound NormalizedMessage; report status/heartbeat per owner; run pytest → green

## 8. Admin API (owner scoping + admin-see-all)

- [x] 8.1 Write failing integration test: `im_admin_api` scopes write/read-by-platform to the admin owner; admin list sees every owner; rows include owner_id; secrets masked (tests/integration/test_im_admin_api.py)
- [x] 8.2 Scope list/read/write by owner (default = admin owner, optional owner_id override); admin list spans owners; include owner_id in responses; update server seams, CLI, user_store wrapper; run pytest → green

## 9. Admin UI

- [x] 9.1 Write failing UI test: IM Connectors tab shows owner column for admin, create attaches to caller owner, secrets masked/no-prefill (tests/integration/test_admin_console_ui.py)
- [x] 9.2 Update connectors tab markup/JS for owner column + owner-scoped create; run pytest → green

## 10. Cleanup + gates

- [x] 10.1 `uv run ruff format src tests && uv run ruff check src tests`
- [x] 10.2 `uv run mypy src`
- [x] 10.3 Full `uv run pytest -q` green
- [x] 10.4 Browser smoke: IM Connectors tab loads, owner column renders for admin, create scoped to owner, no console error
