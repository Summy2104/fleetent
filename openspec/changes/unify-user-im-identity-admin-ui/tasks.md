# Tasks

All UI changes are in `src/fleetent/static/admin.html`; tests are UI-marker assertions
in `tests/integration/test_admin_console_ui.py` and `tests/integration/test_im_admin_api.py`.
Follow the TDD Hard Gate: write failing test → RED → implement → GREEN.

## 1. Remove standalone IM tab, single Users axis

- [ ] 1.1 Write failing tests: no `data-tab="im"`, no `id="tab-im"`, no `id="im-groups"`, no `LOADERS.im`; `im` absent from `TAB_GROUP`/`GROUP_DEFAULT_TAB`; Access group's only tabs are `users`. Update the existing IM-tab assertions (`test_im_users_and_connectors_unified_in_im_tab`, `test_im_loader_renders_unified_view`, `test_ui_has_connectors_in_im_tab_and_add_modal`) to the unified Users axis.
- [ ] 1.2 Implement: delete `#tab-im` section, `loadIm`, `#im-groups`; remove `im` from nav buttons, `TAB_GROUP`, `GROUP_DEFAULT_TAB`, `LOADERS`. Run tests → GREEN.

## 2. Foldable IM identities per User

- [ ] 2.1 Write failing tests: `renderUsers` body joins IM identities by `user_id` (`im_users.user_id`/`user.id`); expander control rendered only when a User has identities; expanded child wires `openBindModal`, `imBlock`, `imRestore` and shows platform/platform_user_id/allowed pill.
- [ ] 2.2 Implement: `loadUsers` fetches `/admin/users` + `/admin/im-users` (+ connectors, task 3) in parallel; build `imByUser`; render row + collapse-by-default child with identity rows; expander only when `imByUser[id]?.length`. Run tests → GREEN.

## 3. Connectors grouped under owning User

- [ ] 3.1 Write failing tests: `renderUsers` body references `owner_id` join for connectors (`connectors.owner_id`/`user.id`); connector child shows status/enabled/masked creds and wires `connEnable`/`connDisable`; "Add connection" create bar (`conn-create-bar`) lives in the Users tab and is admin-gated; connector modal + `CONN_FIELDS` retained.
- [ ] 3.2 Implement: fetch `/admin/im/connectors`; build `connByOwner`; render owned connectors inside the User's expandable child; repoint `connEnable`/`connDisable`/`createConn` refresh to `loadUsers`; keep `openConnModal`/`renderConnFields`/`CONN_FIELDS`. Run tests → GREEN.

## 4. Source filter + badge

- [ ] 4.1 Write failing tests: a source filter control exists in the Users tab; `renderUsers` classifies IM-origin vs human/API (bound identities or `{platform}:{id}` name pattern) and emits a source badge; default shows all sources.
- [ ] 4.2 Implement: add source `<select>`/toggle; classification + badge in `renderUsers`; filter applied client-side with all-sources default. Run tests → GREEN.

## 5. Distinct block semantics

- [ ] 5.1 Write failing tests: whole-User disable control labeled distinctly from per-identity block; user action wires `/users/${id}/block|unblock`, identity action wires `/im-users/${id}/block|restore`; both present with distinct labels.
- [ ] 5.2 Implement: ensure user-level disable (status pill + label "Disable user") and identity-level block (allowed pill + label "Block identity") render as separate controls. Run tests → GREEN.

## 6. Regression + format

- [ ] 6.1 Run `uv run pytest tests/integration/test_admin_console_ui.py tests/integration/test_im_admin_api.py -q` → GREEN.
- [ ] 6.2 Run full gate `uv run pytest -x -q`; `uv run ruff format src tests && uv run ruff check src tests`.
- [ ] 6.3 Browser-verify: single Users tab, expandable Users with identities + connectors, source filter, no IM tab.
