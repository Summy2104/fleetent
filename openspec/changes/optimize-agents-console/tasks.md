## 1. Per-agent OAuth connector binding (store + migration)

- [x] 1.1 Write failing tests: migration creates `agent_oauth_bindings`; store `bind`/`unbind`/`list_connectors_for_agent`/`list_agents_for_connector` (idempotent, per-agent scoped) — run `uv run pytest tests/integration/test_migrations.py tests/integration/test_agent_oauth_binding_store.py -x -q` → red
- [x] 1.2 Add Alembic migration `0NN_add_agent_oauth_bindings` (agent_id, connector_id, created_at, created_by; PK (agent_id, connector_id)); single head
- [x] 1.3 Implement `agent_oauth_binding_store` (named params, db runtime, no ORM) to green
- [x] 1.4 `uv run pytest -x -q` for the two files → green; migration upgrade/downgrade round-trip clean

## 2. Agent-side knowledge-base binding endpoints

- [x] 2.1 Write failing tests in `tests/integration/test_agent_admin_api.py`: GET/POST/DELETE `/admin/agents/{name}/kbs` (list, idempotent bind, unbind, viewer 403, unknown agent 404) → red
- [x] 2.2 Implement the endpoints in `agent_admin_api.py` delegating to `agent_kbs_store` (resolve name→id, agent tenant); reuse role guards → green

## 3. Agent-side OAuth connector binding endpoints

- [x] 3.1 Write failing tests: GET/POST/DELETE `/admin/agents/{name}/bindings/oauth/{connector_id}` (list, idempotent bind, unbind, viewer 403, unknown connector 404) → red
- [x] 3.2 Implement the endpoints in `agent_admin_api.py` over `agent_oauth_binding_store`, validating the connector exists via `connector_config_store` → green
- [x] 3.3 `uv run pytest tests/integration/test_agent_admin_api.py -x -q` → green; `uv run ruff check` + `uv run mypy` on changed backend files clean

## 4. Frontend — Agents card grid + toolbar

- [ ] 4.1 Replace the `#tab-agents` table with a card grid (`connector-grid`/`#ag-grid`), a toolbar (search + status filter tabs) and a result count, mirroring Skills
- [ ] 4.2 Rewrite `loadAgents()`/`renderAgents()` to fetch once and render `agentCardHtml()` cards with status/provenance pills + quick actions; preserve `data-tab="agents"` and admin/viewer gating

## 5. Frontend — agent detail drawer (CRUD + versions)

- [ ] 5.1 Add `#ag-drawer` (reuse `.conn-drawer` classes) opened on card click: metadata (system prompt, allowed tools, model overrides, status, provenance), lifecycle actions (enable/disable/archive/restore/delete/clone), and a Versions section with activate
- [ ] 5.2 Wire **edit**: action in the drawer reads `GET /admin/agents/{name}` to prefill the edit modal and saves via `PATCH /admin/agents/{name}`; create modal keeps the required-template flow

## 6. Frontend — binding management sections in the drawer

- [ ] 6.1 Skills section: bound list + toggle via `GET /admin/agents/{name}/skills` + `PUT /admin/agents/{name}/skills/{skill}`
- [ ] 6.2 Connectors section: MCP servers (options `GET /admin/mcp/servers`, state `GET /admin/agents/{name}/bindings`, `POST`/`DELETE .../bindings/mcp/{id}`) and OAuth connectors (options `GET /admin/connectors`, state + toggle via the new OAuth binding endpoints)
- [ ] 6.3 Knowledge bases section: bound-KB list + bind/unbind via `/admin/agents/{name}/kbs`
- [ ] 6.4 IM section: user bindings and channel bindings list + bind/unbind via the existing user/channel endpoints
- [ ] 6.5 Remove the old `#ag-bind-modal` / `#ag-modal` bindings flow and all dead `agOpenBind`/`ag-bind-*` references

## 7. Tests + cleanup

- [ ] 7.1 Update `tests/integration/test_admin_console_ui.py` agent assertions to the new card/drawer markup + binding sections (drop table/old-modal assertions); keep nav/tab hooks
- [ ] 7.2 `uv run pytest -x -q` (full suite) green; `uv run ruff check src tests` and `uv run mypy src` show no new issues from this change

## 8. Verify

- [ ] 8.1 Browser-verify: agent card grid + search/filter; drawer CRUD + edit; each binding section (skills, MCP + OAuth connectors, KB, IM) manages its bound list; viewer gating
- [ ] 8.2 Archive the change on the feature branch (`/opsx:archive`) after all checkboxes are `[x]`
