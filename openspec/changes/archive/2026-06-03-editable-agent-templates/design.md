## Context

`agent_templates.py` holds three built-in templates as module constants exposed read-only via `GET /admin/agent-templates`. The console's "Templates" button dumps them as JSON. There is no way to edit, add, or remove a template; changes would require a code deploy. Agents themselves are already DB-backed and fully CRUD-able (agent_store + agent_admin_state).

## Goals / Non-Goals

**Goals:**
- Persist templates in the DB so they can be edited at runtime.
- Expose create/edit/delete endpoints + an editable console panel, admin-gated.
- Seed the existing three built-ins so behavior is unchanged on first migrate.

**Non-Goals:**
- No new template fields beyond the current `display_name`/`allowed_tools`/`system_prompt` (templates stay a prefill preset for agent creation; version-config fields like skills_dir are an agent concern, not added here).
- No "create-from-template" wiring change — that flow already reads a template and creates an agent; it keeps working against the store-backed list.
- No protection distinguishing built-in vs custom templates: seeded rows are ordinary editable/deletable rows (simplest model; re-running the migration does not resurrect deleted seeds).

## Decisions

- **Table.** `agent_templates(id TEXT PK, display_name TEXT NOT NULL, allowed_tools TEXT NOT NULL DEFAULT '[]', system_prompt TEXT NOT NULL DEFAULT '', created_at TEXT, updated_at TEXT)`. Alembic migration 034 creates it and `INSERT`s the three built-ins (values inlined in the migration to avoid importing app code).
- **Store.** New `agent_template_store.py` mirroring the `agent_store` conventions: module-level `DB_PATH` is not reused — it goes through the shared DB runtime (`create_database(Settings(...).database_url)`), named params, no ORM, no `_init_db()`. `update_template` uses a sentinel/`None`-means-unchanged pattern and returns the row (or None if missing). `delete_template` returns bool.
- **API.** Template routes move into `agent_console_api.py` next to the existing `GET /agent-templates`. Reads go through an injectable seam so tests can wire the real store (mirrors the agent-def seam pattern). New seams: `list_template_defs`/`get_template_def`/`create_template_def`/`update_template_def`/`delete_template_def`, wired in `server.py` `wire_agent_store_seams()`. `POST` returns 201, dup→409; `PATCH` 200/404; `DELETE` 200/404.
- **agent_templates.py.** Kept as the canonical seed values (referenced by the migration via copy of literals, not import). Console API stops calling `agent_templates.list_templates()` directly; it calls the seam. The module's `get_template` may still back the create-from-template prefill until that flow is repointed at the store (out of scope; both return the same shape).
- **admin.html.** Replace the JSON dump with a rendered template list: each row shows id/display_name with Edit/Delete actions (admin-gated via `IS_VIEWER`), plus a "New template" button. A `#tmpl-modal` captures id (locked on edit)/display_name/allowed_tools (comma list)/system_prompt. JS: `tmplLoad`/`tmplRender`/`tmplCreate`/`tmplEdit`/`tmplSave`/`tmplDelete`.

## Risks / Trade-offs

- **Deleted built-ins don't come back** on re-migrate (migration only seeds on table create). Acceptable: editability implies the admin owns the set.
- **Two readers of templates** during transition (store for console list, constants for create-from-template prefill). Both return identical shape for seeded ids; divergence only for admin-added templates, which the prefill flow can adopt in a follow-up. Documented as out-of-scope.
- **id is user-supplied PK** — validate non-empty; dup → 409 from the store's INSERT failing.
