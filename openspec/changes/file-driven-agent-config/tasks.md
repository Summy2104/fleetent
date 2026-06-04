## 1. Agent file schema + model

- [ ] 1.1 Write failing unit tests for the `agent.yaml` pydantic model: valid file
  parses all fields; missing required field rejected; `name` mismatch vs directory
  rejected; inline `mcp_servers` reuse `McpServerSettings`; defaults (`skills_dir` null,
  `allowed_skills`/`plugins` empty, `bindings.default` false).
- [ ] 1.2 Implement the `AgentFile` model (+ nested `bindings`) in new module
  `fleetent/agent_config.py` with injectable `AGENTS_DIR` constant honoring
  `FLEETENT_AGENTS_DIR`. Make 1.1 green.

## 2. Scan + in-memory index

- [ ] 2.1 Write failing unit tests for `scan()` → `AgentConfigIndex`: builds
  `name→def`, `(platform,channel)→name`, `user→name`, default set; empty/missing dir
  yields empty index with no error; directory-name vs in-file-name mismatch fails fast.
- [ ] 2.2 Implement `scan()` and `AgentConfigIndex` lookups (`get(name)`,
  `agent_for_channel`, `agent_for_user`, `default_agent`). Make 2.1 green.
- [ ] 2.3 Write failing unit tests for conflict detection: two agents binding the same
  channel fails fast; same user bound twice fails fast; more than one `default` fails
  fast; error message names the offending agents/channel.
- [ ] 2.4 Implement conflict detection in `scan()`. Make 2.3 green.
- [ ] 2.5 Write failing unit tests for secret rejection: inline token-like value in
  `mcp_servers` rejected (file + field named); `api_key_env` reference accepted.
- [ ] 2.6 Implement secret scan in `scan()` reusing `config_validation._looks_inline_secret`.
  Make 2.5 green.

## 3. snapshot.py rewired to the file index (API/shape preserved)

- [ ] 3.1 Write failing unit tests: `load_active(name)` returns an `AgentSnapshot` built
  from the file (identity = name); unknown name returns `None`; `AgentSnapshot` shape
  unchanged; `filter_tool_schemas` behavior unchanged.
- [ ] 3.2 Rewire `load_active` to read the index instead of `agent_store`. Make 3.1 green.
- [ ] 3.3 Write failing unit tests for `resolve_mcp_servers`: inline `mcp_servers`
  overlaid on global defaults with no DB call (DB rigged to raise).
- [ ] 3.4 Implement inline-MCP overlay in `resolve_mcp_servers`. Make 3.3 green.
- [ ] 3.5 Write failing unit tests for `resolve_agent_for_request` precedence served
  from the index: channel > user > default > bare run; `connector_scope` returns the
  agent name.
- [ ] 3.6 Rewire `resolve_agent_for_request` and `connector_scope` to the index. Make
  3.5 green.

## 4. Wiring into server + CLI

- [ ] 4.1 Write failing integration test: FastAPI lifespan scans the agents dir once at
  startup; CLI `run()` scans per invocation (`FLEETENT_AGENTS_DIR` honored).
- [ ] 4.2 Wire `scan()` into the FastAPI lifespan and CLI `run()`. Make 4.1 green.

## 5. End-to-end + zero-DB guarantee

- [ ] 5.1 Write failing integration test (red): `resolve_agent_for_request` end-to-end
  from a `tmp_path` agents dir resolves the right agent across channel/user/default cases.
- [ ] 5.2 Write failing integration test (red): with the database layer monkeypatched to
  raise on any access, runtime resolution + a stubbed run complete without raising
  (zero-DB proof).
- [ ] 5.3 Land any remaining wiring/fixtures so 5.1 and 5.2 turn green.

## 6. Closeout

- [ ] 6.1 Add a `config/agents/<name>/agent.yaml.example` documenting the schema.
- [ ] 6.2 Run `uv run ruff format src tests && uv run ruff check src tests` and
  `uv run mypy src` (no new errors over baseline).
- [ ] 6.3 Run full suite `uv run pytest -x -q` green.
