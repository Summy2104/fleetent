## 1. Materialize agent home on create/update

- [ ] 1.1 Write failing tests: platform create/update writes `FLEETENT_HOME/<agent-id>/agent.yaml`
  from the authored definition (prompt/tools/skills/mcp/connectors + `access`); seeds a
  `.env` scaffold (env-var names only, no plaintext); update rewrites agent.yaml but
  preserves operator `.env` values.
- [ ] 1.2 Implement home materialization in agent create/update (reuse the agent home
  schema + per-agent access from per-agent-im-access). Make 1.1 green.

## 2. Start/stop controller (spawn, no monitoring)

- [ ] 2.1 Write failing tests (mock subprocess spawn): start spawns
  `fleetent agent run <name>` and records the PID; stop terminates the tracked process;
  a process that exits is reported not-running and is NOT restarted.
- [ ] 2.2 Implement the start/stop controller (spawn/terminate + in-memory PID tracking,
  no probe/restart). Make 2.1 green.

## 3. Admin endpoints

- [ ] 3.1 Write failing integration tests: `POST /admin/agents/<name>/start` materializes
  (if needed) + spawns; `/stop` terminates; status reflects tracked-running vs not.
- [ ] 3.2 Add the start/stop/status admin endpoints wired to the controller. Make 3.1
  green.

## 4. Closeout

- [ ] 4.1 `uv run ruff format src tests && uv run ruff check src tests` and
  `uv run mypy src` (no new errors over baseline).
- [ ] 4.2 Full suite `uv run pytest -x -q` green.
