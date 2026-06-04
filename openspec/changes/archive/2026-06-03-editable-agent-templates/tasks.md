## 1. Migration: agent_templates table + seed

- [x] 1.1 Write failing test (tests/integration/test_agent_template_store.py): after migrations, an `agent_templates` table exists with rows for `readonly-qa`/`ops`/`support` and their built-in fields
- [x] 1.2 Add `migrations/versions/034_add_agent_templates.py` (down_revision 033) creating the table and seeding the three built-ins → test green

## 2. Store: agent_template_store CRUD

- [x] 2.1 Write failing tests (tests/integration/test_agent_template_store.py): list returns seeds; create persists; create dup raises; update overrides only provided field; update missing returns falsey; delete returns True/removes; delete missing returns False
- [x] 2.2 Implement `agent_template_store.py` (list_templates/get_template/create_template/update_template/delete_template; named params; shared DB runtime; no ORM) → tests green

## 3. API: template CRUD endpoints

The template store is self-contained (no injected deps), so the routes call
`agent_template_store` directly — no server.py seam wiring needed.

- [x] 3.1 Write failing tests (tests/integration/test_agent_console_api.py): GET lists via store (seeded built-ins); POST creates (201) + dup 409; PATCH edits (200) + missing 404; DELETE removes (200) + missing 404; viewer write → 403; audit entries written
- [x] 3.2 Add `POST/PATCH/DELETE /admin/agent-templates` routes (admin-gated, audit) and repoint GET at `agent_template_store` → tests green

## 4. admin.html template editing UI

- [x] 4.1 Write failing UI assertion tests (tests/integration/test_admin_console_ui.py): `#tmpl-modal` + fields present; `tmplCreate`/`tmplEdit`/`tmplSave`/`tmplDelete` functions present; POST/PATCH/DELETE `/agent-templates` wired; New template + Edit/Delete actions admin-gated (`IS_VIEWER`)
- [x] 4.2 Replace JSON dump with rendered editable template list + `#tmpl-modal` and JS (tmplLoad/tmplRender/tmplCreate/tmplEdit/tmplSave/tmplDelete) → tests green

## 5. Gate + finalize

- [x] 5.1 Run `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src`
- [x] 5.2 Run full suite `uv run pytest -x -q` → all green
