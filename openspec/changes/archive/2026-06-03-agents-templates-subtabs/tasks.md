## 1. In-page sub-tabs

- [x] 1.1 Update/replace failing tests (tests/integration/test_admin_console_ui.py): no `data-tab="templates"` sidebar item and no `id="tab-templates"` section; Agents page has `agSubTab` sub-tab switcher with `Agents`/`Templates` panes (`#ag-pane`/`#tmpl-pane`); template list/modal/CRUD functions/endpoints still present; write controls admin-gated
- [x] 1.2 In admin.html: remove the Templates sidebar nav item, the `#tab-templates` section, the `templates` entry in `TAB_GROUP`, and the standalone `LOADERS.templates`; add sub-tab buttons in the Agents page header and `#ag-pane`/`#tmpl-pane` wrappers; add `agSubTab(name)` that toggles panes and lazy-loads templates; point Refresh at the active sub-tab → tests green

## 2. Gate + finalize

- [x] 2.1 Run `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src`
- [x] 2.2 Run full suite `uv run pytest -x -q` → all green
