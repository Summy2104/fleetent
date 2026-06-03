## Why

The admin console can list, enable/disable, archive/restore, clone, and inspect agents, but it cannot **create**, **read full definition**, **edit**, or **hard-delete** an agent. The console/apply seams that would persist these operations (`get_agent_def`, `create_agent_def`, `update_agent_def`) are never wired to `agent_store` in `server.py`, so clone/apply are inert in production. Agent CRUD is incomplete end-to-end.

## What Changes

- Add `agent_store.delete_agent(name)` — hard delete of `agents` + `agent_versions` rows in one transaction.
- Wire the unwired seams in `server.py`: console `get_agent_def`/`create_agent_def` and apply `get_agent_def`/`create_agent_def`/`update_agent_def` → `agent_store`. Fixes inert clone/apply.
- New REST endpoints in `agent_console_api.py`:
  - `POST /admin/agents` — create agent def + `agent_admin_state` row (provenance `adhoc`, enabled).
  - `GET /admin/agents/{name}` — full agent definition (active version runtime fields).
  - `PATCH /admin/agents/{name}` — edit via `agent_store.create_version` (new immutable snapshot, activated); `mark_drift` if managed.
  - `DELETE /admin/agents/{name}` — hard delete, blocked when user/channel bindings reference it (same protection posture as archive).
- Admin UI (`admin.html`): "New agent" button in the Agents bar; Edit + Delete row actions; a create/edit modal (name, system_prompt, allowed_tools); `agCreate`/`agEdit`/`agSave`/`agDelete` JS. Admin-gated.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `agent-definition`: add `delete_agent` to the store contract (hard delete agents + versions).
- `agent-admin-api`: add create / read-full / update / delete REST endpoints with role + binding-protection rules; require seams wired to `agent_store`.
- `agent-admin-ui`: add create button, edit/delete row actions, and the create/edit modal.

## Impact

- Code: `src/fleetent/agent_store.py`, `src/fleetent/platform/agent_management_console/agent_console_api.py`, `src/fleetent/platform/askit_console/agent_apply_api.py` (seam types), `src/fleetent/server.py` (wire seams), `src/fleetent/static/admin.html`.
- APIs: 4 new `/admin/agents` routes; clone/apply become functional once seams wired.
- Data: no schema change — reuses `agents`, `agent_versions`, `agent_admin_state`.
