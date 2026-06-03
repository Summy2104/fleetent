## 1. Templates tab UI

- [x] 1.1 Write failing tests (tests/integration/test_admin_console_ui.py): `data-tab="templates"` nav item present; `id="tab-templates"` section present; `LOADERS.templates` registered; Agents tab no longer has a "Templates" toggle (`tmplToggle` gone); template modal + CRUD functions + endpoints still present
- [x] 1.2 In admin.html: add Templates nav item under the Agents group; add `#tab-templates` section holding the template create bar, list table, and error; move `#tmpl-modal` (or keep it shared); remove the inline `#ag-templates-panel` and its "Templates" toggle button from the Agents tab; replace `tmplToggle()` with `LOADERS.templates = () => tmplLoad()`; add `templates: "agents"` to `TAB_GROUP` → tests green

## 2. Gate + finalize

- [x] 2.1 Run `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src`
- [x] 2.2 Run full suite `uv run pytest -x -q` → all green
