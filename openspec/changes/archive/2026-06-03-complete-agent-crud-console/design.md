## Context

`agent_store` uses an immutable-snapshot model: `agents` row + `agent_versions` rows; `active_version_id` points at the live snapshot. `create_version` is the canonical edit path (copies active, overrides given fields, activates). The console agent list reads `agent_admin_store.list_states()` (a side-table keyed by agent_name carrying status/provenance/drift), NOT the `agents` table — so a created def must also get a state row to be visible.

Two API modules expose agent admin: `agent_console_api.py` (`/admin`) and `agent_apply_api.py` (`/admin/agents`). Both define module-level seam stubs (`get_agent_def`, `create_agent_def`, `update_agent_def`) returning None/0 so tests can monkeypatch them, but `server.py` never assigns the real implementations — clone and apply are inert in production.

## Goals / Non-Goals

**Goals:**
- Full agent CRUD reachable from the admin console: create, read full def, edit, hard delete.
- Wire the seams so clone/apply work in production.
- Preserve immutable-snapshot semantics (edit = new version).
- Honor existing auth posture (viewer read, admin write) and binding-reference protection.

**Non-Goals:**
- No schema migration (reuse existing tables).
- No change to versioning/binding endpoints already present.
- No soft-delete redesign — archive already covers reversible removal; DELETE is a true hard delete.

## Decisions

- **CREATE** = `POST /admin/agents` body `{name, system_prompt?, allowed_tools?}` → `agent_store.create_agent(...)` then `agent_admin_store.set_provenance(name, "adhoc")` + `enable(name)` so it appears in the list. 409 if name exists. 201 on success returning the def.
- **READ** = `GET /admin/agents/{name}` → `agent_store.get_by_name`; 404 if absent. Returns active-version runtime fields (system_prompt, allowed_tools, etc.).
- **UPDATE** = `PATCH /admin/agents/{name}` body subset of editable fields → `agent_store.create_version(name, ...)` (only provided fields overridden, activated). If the agent_admin_state provenance is `managed`, call `mark_drift` (UI edited a managed def). 404 if absent.
- **DELETE** = `DELETE /admin/agents/{name}` → blocked (409) when `agent_admin_store.is_referenced(name)` (user/channel bindings); else `agent_store.delete_agent(name)` + `agent_admin_store.delete_state(name)`. Require `X-Confirm: true` (428 otherwise), matching archive's destructive-action guard.
- **Store**: new `agent_store.delete_agent(name)` deletes `agent_versions` then `agents` in one transaction (FK-safe order); returns bool (False if not found). New `agent_admin_store.delete_state(name)` removes the side-table row.
- **Seams wired in server.py** after `include_router`: console `get_agent_def = lambda n: _agent_def_dict(agent_store.get_by_name(n))`, `create_agent_def = agent_store.create_agent`-adapter; apply's three seams → agent_store equivalents. A shared `_agent_def_dict` helper serializes an `Agent` to the dict shape the seams promise.
- **UI**: "New agent" button in `ag-create-bar` (admin only). Row actions gain Edit/Delete (admin only). One modal does both create and edit (title + hidden mode flag); fields name (readonly on edit), system_prompt (textarea), allowed_tools (comma list). `agCreate` opens blank, `agEdit` fetches GET then prefills, `agSave` POST or PATCH by mode, `agDelete` confirms then DELETE with `X-Confirm`.

## Risks / Trade-offs

- Hard delete is irreversible; mitigated by binding-protection + `X-Confirm` header. Archive remains the reversible default.
- Wiring seams changes clone/apply from no-op to live writes — covered by tests asserting persistence.
- `allowed_tools` free-text comma entry can produce unknown tool names; out of scope to validate against the registry here (existing endpoints don't either).
