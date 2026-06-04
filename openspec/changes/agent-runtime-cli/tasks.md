## 1. Agent-runtime boot/app (factored from server.py)

- [x] 1.1 Write failing tests: an agent-runtime boot routine scans a single agent home,
  starts that agent's IM connectors (mock adapters), starts session/MCP as needed, and
  exposes the agent loop — with no `/admin/*` and no dependency on the platform app.
- [x] 1.2 Factor the agent+IM boot out of `server.py` into an agent-scoped runtime
  (shared libs reused). Make 1.1 green; keep `uvicorn fleetent.server:app` still working.

## 2. `fleetent agent run` CLI

- [x] 2.1 Write failing tests: `fleetent agent run <home>` resolves the home and boots the
  runtime (mock boot); `--port` mounts HTTP/ws, absent `--port` opens no HTTP listener.
- [x] 2.2 Implement the `agent run` subcommand (home resolution + foreground boot +
  optional `--port`). Make 2.1 green.

## 3. One-shot CLI applies the deployed agent

- [ ] 3.1 Write failing test: `run_sync` applies the resolved home/default agent's
  `system_prompt`/`allowed_tools`/`allowed_skills` (not the generic default).
- [ ] 3.2 Rewire `run_sync` to resolve + apply the home agent. Make 3.1 green.

## 4. Closeout

- [ ] 4.1 Migrate/adjust affected server/IM tests for the factored runtime.
- [ ] 4.2 `uv run ruff format src tests && uv run ruff check src tests` and
  `uv run mypy src` (no new errors over baseline).
- [ ] 4.3 Full suite `uv run pytest -x -q` green.
