## 1. Update UI marker tests (red)

- [x] 1.1 In `tests/integration/test_admin_console_ui.py`, write/adjust failing assertions for the consolidated layout: `data-tab="connectors"` and `id="tab-connectors"` are ABSENT; `connectors` is removed from the reachable-tab lists in `test_existing_tabs_still_reachable` and `test_sidebar_all_modules_reachable`.
- [x] 1.2 Add a test asserting the connector block lives inside the IM tab: `conn-body`, `conn-create-bar`, and the connectors `page-header` ("IM Connectors") appear within the `#tab-im` section; the owner-column tests still pass against the relocated table.
- [x] 1.3 Add a test asserting `LOADERS.im` triggers both lists (references both `loadIm` and `loadConn`) and that `LOADERS.connectors` is no longer registered / `connectors` is absent from `TAB_GROUP`.
- [x] 1.4 Run `uv run pytest tests/integration/test_admin_console_ui.py -x -q` and confirm RED.

## 2. Consolidate the markup (green)

- [x] 2.1 Remove the `<button data-tab="connectors" …>IM Connectors</button>` nav item from the "Models & Connectors" group in `admin.html`.
- [x] 2.2 Move the inner markup of `#tab-connectors` (intro row, `conn-create-bar`, connectors table + `conn-body`) into the `#tab-im` section below the IM-users block, each under its own `page-header`; delete the now-empty `#tab-connectors` section.
- [x] 2.3 Run `uv run pytest tests/integration/test_admin_console_ui.py -x -q`; iterate to GREEN for markup assertions.

## 3. Rewire the navigation JS (green)

- [x] 3.1 Remove `connectors` from `TAB_GROUP`; set `LOADERS.im = () => { loadIm(); loadConn(); }` and remove the `LOADERS.connectors` registration.
- [x] 3.2 Confirm `switchTab`/`switchGroup` need no change (single IM section; `GROUP_DEFAULT_TAB.access` stays `users`); keep `openConnModal()` trigger intact.
- [x] 3.3 Run `uv run pytest tests/integration/test_admin_console_ui.py -x -q` and confirm GREEN.

## 4. Verify full suite + quality gate

- [x] 4.1 Run `uv run pytest -x -q` (only the known pre-existing `test_stats_admin_api::test_export_and_report_audited` failure permitted).
- [x] 4.2 Run `uv run ruff format src tests && uv run ruff check src tests`.
- [x] 4.3 Run `uv run openspec validate merge-im-connectors-ui-into-im-users --strict`.
