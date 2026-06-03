## 1. Credential field schema (im_connector_config)

- [x] 1.1 Write failing tests for expanded `PLATFORM_CONFIG_KEYS`: slack has `bot_token`/`signing_secret`/`app_token`; whatsapp has `phone_number_id`/`access_token`/`verify_token`/`business_account_id`; telegram has `bot_token` (tests/integration/test_im_connector_config.py)
- [x] 1.2 Write failing test that `resolve_masked` masks a whatsapp `access_token` to last 4 chars
- [x] 1.3 Expand `PLATFORM_CONFIG_KEYS` and `_ENV_MAP` to satisfy 1.1–1.2 (run pytest → green)

## 2. Create-connector API (POST /admin/im/connectors)

- [x] 2.1 Write failing tests: admin POST creates a new `whatsapp` connector with config (returns masked); POST for existing platform updates config without duplicate row; viewer gets 403; unknown platform rejected (tests/integration/test_im_admin_api.py)
- [x] 2.2 Add `CreateConnectorBody` + `POST /admin/im/connectors` (admin-only, validates platform ∈ telegram/slack/whatsapp, calls `set_config`) to im_admin_api.py (run pytest → green)

## 3. Admin console connector UI (admin.html)

- [x] 3.1 Write failing tests asserting admin.html ships the connectors UI: an "Add connection" control, a platform `<select>` with telegram/slack/whatsapp, the per-platform field ids/names matching `PLATFORM_CONFIG_KEYS` (slack 3 fields, whatsapp 4, telegram 1), enable/disable wiring, and viewer-hidden management controls (tests/integration/test_im_admin_api.py UI assertions)
- [x] 3.2 Add connectors section + add-connection modal with platform dropdown and dynamic per-platform credential fields to admin.html; wire create/list/enable/disable to `/admin/im/connectors`; gate controls to admin (run pytest → green)
- [x] 3.3 Browser-verify the modal in the running console: dropdown switches fields per platform, submit POSTs credentials, list shows masked values, enable/disable work

## 4. Gates

- [x] 4.1 `uv run ruff format src tests && uv run ruff check src tests`
- [x] 4.2 `uv run mypy src`
- [x] 4.3 Full `uv run pytest -q` green
