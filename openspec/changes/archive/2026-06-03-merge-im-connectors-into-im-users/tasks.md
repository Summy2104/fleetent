## 1. IM module package skeleton + public API

- [x] 1.1 Write failing test `tests/unit/test_im_module_public_api.py`: importing `fleetent.platform.im_gateway_management` exposes the unified public API names (identity: `get_or_create`, `check_allowed_by_user_id`, `block_im_user`, `restore_im_user`, `rebind_im_identity`, `list_im_identities`, `list_all`, `list_pending`; connector: `upsert_connector`, `get_connector`, `list_connectors`, `report_status`, `set_enabled`, `set_allowlist_enforced`; config: `resolve`, `resolve_masked`, `set_config`, `seed_from_env`; manager: `ConnectorManager`; allowlist: `add_entry`, `remove_entry`, `list_entries`, `is_allowed`; admin: `router`) and a single `DB_PATH`
- [x] 1.2 Add `__init__.py` public API re-exports + a single `DB_PATH` re-export from `user_store`; run test green

## 2. Identity submodule (ex im_user_store)

- [x] 2.1 Write failing test `tests/unit/test_im_identity_submodule.py`: `from fleetent.platform.im_gateway_management import identity` provides `get_or_create`/allowlist/workbench fns and `identity.DB_PATH` is monkeypatchable
- [x] 2.2 Move `im_user_store.py` body into `platform/im_gateway_management/identity.py` (behavior unchanged); run test green
- [x] 2.3 Write failing shim test: `import fleetent.im_user_store as legacy` and assert `legacy.get_or_create is identity.get_or_create`
- [x] 2.4 Replace `src/fleetent/im_user_store.py` with re-export-only shim (`# noqa: F401`); run shim test green

## 3. Connector store submodule

- [x] 3.1 Write failing test `tests/unit/test_im_connector_store_submodule.py`: `from …im_gateway_management import connector_store` exposes store fns; `connector_store.DB_PATH` monkeypatchable
- [x] 3.2 Rename/move `im_connector_store.py` → `connector_store.py` (behavior unchanged); run test green
- [x] 3.3 Write failing shim test: old `…im_gateway_management.im_connector_store` re-exports same objects
- [x] 3.4 Replace `im_connector_store.py` with re-export-only shim; run shim test green

## 4. Connector config submodule

- [x] 4.1 Write failing test: `from …im_gateway_management import connector_config` exposes `resolve/resolve_masked/set_config/seed_from_env`; masking + env-map preserved
- [x] 4.2 Move `im_connector_config.py` → `connector_config.py` (imports updated to `connector_store`); run test green
- [x] 4.3 Write failing shim test for old `im_connector_config` path; replace with re-export shim; run green

## 5. Connector manager submodule

- [x] 5.1 Write failing test: `from …im_gateway_management import connector_manager` exposes `ConnectorManager` with start/stop/reload/start_all_enabled behavior preserved
- [x] 5.2 Move `im_connector_manager.py` → `connector_manager.py` (imports updated); run test green
- [x] 5.3 Write failing shim test for old `im_connector_manager` path; replace with re-export shim; run green

## 6. Channel allowlist submodule

- [x] 6.1 Write failing test: `from …im_gateway_management import channel_allowlist` exposes `add_entry/remove_entry/list_entries/is_allowed`; enforcement semantics preserved
- [x] 6.2 Move `im_channel_allowlist.py` → `channel_allowlist.py` (imports updated to `connector_store`); run test green
- [x] 6.3 Write failing shim test for old `im_channel_allowlist` path; replace with re-export shim; run green

## 7. Admin API submodule + server wiring

- [x] 7.1 Write failing test: `from …im_gateway_management import admin_api` exposes `router` with prefix `/admin/im`, admin-only + masked reads unchanged; `start_connector`/`stop_connector` seams present
- [x] 7.2 Move `im_admin_api.py` → `admin_api.py` (imports updated to sibling submodules); update `server.py` to use `admin_api.router` (route paths unchanged); run test green
- [x] 7.3 Write failing shim test for old `im_admin_api` path; replace with re-export shim; run green

## 8. Importer migration + boundary + closeout

- [x] 8.1 Migrate first-party src importers to canonical paths (`im_gateway/{slack,telegram,normalizer}.py`, `user_store.py`, `governance/blocklist.py`, `platform/user_management/user_admin_api.py`, `platform/admin_cli/{im,im_connectors}.py`); keep shims in place; run `uv run pytest tests/unit tests/integration -q` green
- [x] 8.2 Migrate test imports to canonical paths (identity + connector + allowlist + admin suites); run affected suites green
- [x] 8.3 Verify `module-boundaries` delta: add an assertion-style integration test or doc check that no first-party src module (outside the IM module) imports IM internal files directly
- [x] 8.4 Run full `uv run pytest -x -q`, `uv run ruff format/check src tests`, `uv run mypy src`; fix any regressions
