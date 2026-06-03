# Tasks

## 1. Store: hard delete

- [x] 1.1 Write failing tests for `agent_store.delete_agent` (deletes agents + agent_versions in one transaction → returns True; unknown name → returns False; no rows touched)
- [x] 1.2 Implement `agent_store.delete_agent(name) -> bool` (named params, FK-safe order, single transaction) to pass tests
- [x] 1.3 Write failing test for `agent_admin_store.delete_state(name)` (removes side-table row; idempotent on missing)
- [x] 1.4 Implement `agent_admin_store.delete_state(name)` to pass

## 2. API: create / read-full / update / delete endpoints

- [x] 2.1 Write failing tests for `POST /admin/agents` (201 + def + state row provenance=adhoc/enabled; 409 dup name; 403 viewer)
- [x] 2.2 Implement `POST /admin/agents` in `agent_console_api.py` to pass
- [x] 2.3 Write failing tests for `GET /admin/agents/{name}` (200 with active-version fields; 404 missing)
- [x] 2.4 Implement `GET /admin/agents/{name}` to pass
- [x] 2.5 Write failing tests for `PATCH /admin/agents/{name}` (200 + new active version with overridden field; 404 missing; managed → drift set)
- [x] 2.6 Implement `PATCH /admin/agents/{name}` (via `agent_store.create_version`, mark_drift if managed) to pass
- [x] 2.7 Write failing tests for `DELETE /admin/agents/{name}` (428 without X-Confirm; 409 when bindings reference; 200 removes def + state; viewer 403)
- [x] 2.8 Implement `DELETE /admin/agents/{name}` to pass

## 3. Wire seams in server.py

- [x] 3.1 Write failing test that clone persists via wired seam (configured app: source created via store, clone → `agent_store.get_by_name(new_name)` returns copy)
- [x] 3.2 Wire console + apply seams (`get_agent_def`/`create_agent_def`/`update_agent_def`) to `agent_store` in `server.py`; add `_agent_def_dict` serializer to pass

## 4. Admin UI

- [x] 4.1 Write failing `test_admin_console_ui` assertions: "New agent" button in agents bar, per-row Edit + Delete actions admin-gated, create/edit modal with name/system_prompt/allowed_tools fields, `agCreate`/`agEdit`/`agSave`/`agDelete` present
- [x] 4.2 Implement admin.html changes (bar button, row actions, modal, JS funcs) to pass

## 5. Gate

- [x] 5.1 `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src`
- [x] 5.2 Full suite `uv run pytest -x -q` green
