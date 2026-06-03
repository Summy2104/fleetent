# Tasks

## 1. MCP binding storage (migration + store)

- [x] 1.1 Write failing tests: migration adds/drops `agent_mcp_servers`
  (`tests/integration/test_migrations.py`) and store bind/unbind/list/idempotent
  behavior (`tests/integration/test_agent_mcp_store.py`).
- [x] 1.2 Add Alembic migration (revision after 035) creating `agent_mcp_servers`
  `(agent_id, server_id, created_at, created_by)` PK `(agent_id, server_id)`; downgrade
  drops it. Implement store functions (`bind_mcp_server`, `unbind_mcp_server`,
  `list_mcp_servers_for_agent`) via the shared DB runtime + named params.

## 2. Skill binding agent-side store reads

- [x] 2.1 Write failing tests for an agent-centric skills view that returns every known
  skill with the agent's enabled flag (`tests/integration/test_skill_admin_store.py` or
  a new test), reusing `skill_admin_store`.
- [x] 2.2 Implement the agent-centric skills listing (compose `skill_registry` known
  skills with `agent_skills` rows) to pass the tests.

## 3. Agent admin API: binding read + MCP + agent-side skills

- [x] 3.1 Write failing API tests (`tests/integration/test_agent_admin_api.py` or
  existing agent api test): `GET /admin/agents/{name}/bindings` shape + 404;
  `GET /admin/agents/{name}/skills`; `PUT /admin/agents/{name}/skills/{skill}`;
  `POST`/`DELETE /admin/agents/{name}/bindings/mcp/{server_id}` incl. 404 unknown server
  and viewer-forbidden.
- [x] 3.2 Implement the routes in `agent_admin_api.py` (admin-only writes, audited;
  validate `server_id` against `GET /admin/mcp/servers`).

## 4. Runtime: skill index allowlist

- [x] 4.1 Write failing unit test: `SkillIndex(allowed={...})` only matches allowed
  skills (`tests/unit/test_skill_registry.py`).
- [x] 4.2 Add `allowed: set[str] | None` to `SkillIndex.__init__`; filter the index.

## 5. Runtime: agent_loop resolves bindings

- [x] 5.1 Write failing unit tests (`tests/unit/test_agent_loop.py`): skill injection
  restricted to enabled `agent_skills` when present, fallback to all when none; MCP set
  is the union of snapshot `mcp_server_ids` and `agent_mcp_servers`; both run and
  run_stream paths.
- [x] 5.2 Wire `agent_loop` (run + run_stream) to resolve skill + MCP bindings and pass
  `allowed` to `SkillIndex` and the unioned set to `filter_tool_schemas`.

## 6. Admin UI: Bindings modal sections

- [x] 6.1 Write failing UI-string tests (`tests/integration/test_admin_console_ui.py`):
  Bindings modal contains Skills toggles wired to `PUT .../skills/`, MCP toggles wired to
  `POST`/`DELETE .../bindings/mcp/`, a channels list from `GET .../bindings`, and all
  binding write controls gated by `IS_VIEWER`.
- [x] 6.2 Implement the modal sections in `admin.html` (load on open, render toggles +
  channel list, wire handlers).

## 7. Sync + finalize

- [x] 7.1 Run `uv run ruff format src tests && uv run ruff check src tests` and
  `uv run mypy src`; fix issues.
- [x] 7.2 Run `uv run pytest -x -q` (full suite green) and `openspec validate
  expand-agent-bindings`.
