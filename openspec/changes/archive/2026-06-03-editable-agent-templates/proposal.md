## Why

Agent templates are hardcoded module constants in `agent_templates.py` — read-only, not in the DB, not editable via the API or console. Admins want to tailor the recommended `system_prompt`/`allowed_tools` presets to their org and add their own templates. "Modify a template" is meaningless without persistence, so templates must move to a store-backed, editable model.

## What Changes

- New `agent_templates` table (Alembic migration 034) seeded with the three current built-ins (`readonly-qa`, `ops`, `support`).
- New `agent_template_store` (named-params SQL, no ORM, schema owned by Alembic) with `list_templates`/`get_template`/`create_template`/`update_template`/`delete_template`.
- `GET /admin/agent-templates` reads from the store (was: module constants).
- `POST /admin/agent-templates` to create a template (`{id, display_name, allowed_tools, system_prompt}`), 201 / 409 on duplicate id.
- `PATCH /admin/agent-templates/{id}` to edit a template (subset of `display_name`/`allowed_tools`/`system_prompt`), 200 / 404.
- `DELETE /admin/agent-templates/{id}` to remove a template, 200 / 404. Write ops require `admin`/`built_in_admin`; reads allow `viewer`+. Every write emits an `audit_log` entry.
- admin.html: templates panel becomes editable — list with Edit/Delete actions and a "New template" control (admin-gated); a template modal capturing id/display_name/allowed_tools/system_prompt.
- `agent_templates.py` constants become the migration seed source only (kept for seed values); console API no longer reads them directly at request time.

## Capabilities

### New Capabilities

- `agent-templates`: store-backed, editable agent templates (storage schema + store CRUD behavior).

### Modified Capabilities

- `agent-admin-api`: the template endpoint requirement extends from list-only to full CRUD, store-backed.
- `agent-admin-ui`: the templates panel becomes editable (create/edit/delete), admin-gated.

## Impact

- Code: new `migrations/versions/034_add_agent_templates.py`, new `agent_template_store.py`, `agent_console_api.py` (template routes calling the store directly — the store is self-contained, so no server.py seam wiring is needed), `static/admin.html` (template modal + JS).
- DB: new `agent_templates` table; seeded built-ins. No change to `agents`/`agent_versions`.
- Auth/role gating unchanged in shape (write=admin, read=viewer+).
