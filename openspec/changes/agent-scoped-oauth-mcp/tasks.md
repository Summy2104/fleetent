## 1. Schema (Alembic)

- [ ] 1.1 Write failing migration test: fresh `upgrade head` yields `connectors.agent_id` (nullable) and an `agent_mcp_servers` table with McpServerConfig fields + `agent_id`; downgrade removes both; existing connector rows survive as `agent_id IS NULL`
- [ ] 1.2 Add Alembic migration: `ALTER TABLE connectors ADD COLUMN agent_id` (nullable) + `create_table agent_mcp_servers`; downgrade drops column + table; run migration test green

## 2. Connector store scoping

- [ ] 2.1 Write failing tests for `connector_config_store`: add/get/list scoped by `agent_id`; agent-owned overrides global default; duplicate within same agent scope rejected; `client_secret` still stripped; null-scope returns global defaults
- [ ] 2.2 Implement scoped store: `agent_id` param on add/get/list, resolution = agent row else global default; named params; run tests green

## 3. Agent-scoped MCP server store

- [ ] 3.1 Write failing tests for new `agent_mcp_server_store`: CRUD scoped by `agent_id`; list resolves agent-owned overlaid on yaml/global defaults; duplicate per scope rejected
- [ ] 3.2 Implement `agent_mcp_server_store` over the DB runtime boundary (named params, no ORM); run tests green

## 4. MCP client re-keying by scope

- [ ] 4.1 Write failing tests: `_active_sessions` / `_server_registry` keyed by `(scope, server_id)`; two scopes for same `server_id` get distinct sessions/credentials; null scope maps to global default; `call_tool`/dispatch take scope
- [ ] 4.2 Refactor `integrations/mcp/client.py` to scope-keyed maps + scope param on register/call; keep AsyncExitStack shutdown; preserve lazy stdio reuse; run tests green

## 5. Runtime resolution

- [ ] 5.1 Write failing tests for `agent_runtime`: snapshot resolves agent's effective MCP server set (owned overlaid on defaults) and connector scope; `filter_tool_schemas` unchanged for visibility
- [ ] 5.2 Implement resolution in `agent_runtime` wiring scope into the snapshot; run tests green

## 6. Dispatch-time isolation guard

- [ ] 6.1 Write failing tests: dispatch of `server__tool` whose `server_id` is not in the agent's resolved scope is rejected (no global session used); allowed scope dispatch uses the agent's session/credential
- [ ] 6.2 Implement dispatch guard in agent_loop/tool dispatch using the resolved scope; run tests green

## 7. Admin API + UI

- [ ] 7.1 Write failing tests: connector directory + MCP server list expose owning agent and accept an agent filter; authorization-matrix query scoped to owning agent; viewer still 403 on writes
- [ ] 7.2 Implement admin API agent filter + owner column in `connector_admin_api` and MCP server admin; run tests green
- [ ] 7.3 Write failing UI-marker tests for `admin.html`: connector/MCP tables show Owner column + agent filter control
- [ ] 7.4 Implement admin.html markup/JS for owner column + agent filter; run UI-marker tests green

## 8. Integration + closeout

- [ ] 8.1 Write failing end-to-end isolation test: agent A and agent B with same `github` connector/MCP server + different credentials route to separate sessions; B's call not satisfied by A's authorization
- [ ] 8.2 Make the e2e test green
- [ ] 8.3 Run full `uv run pytest -x -q`, `uv run ruff format/check src tests`, `uv run mypy src`; fix any regressions
