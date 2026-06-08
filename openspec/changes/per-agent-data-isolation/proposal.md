## Why

Each standalone `fleetent agent run <id>` process writes runtime data (sessions, DB, logs,
diagnostics, IM approvals) to the shared global `FLEETENT_HOME/data/` directory. When
multiple agents are deployed under the same `FLEETENT_HOME`, their data collides — sessions
and traces from different agents are indistinguishable, and deleting or archiving one agent's
data requires manual surgery on a shared directory.

## What Changes

- Add `paths.agent_data_dir(agent_id: str) -> Path` returning `agents/<id>/data/`
- In `agent_app.boot()`, immediately after `home_dir` is resolved, redirect all per-agent
  runtime data paths to `home_dir / "data"`:
  - `session.manager.SESSIONS_DIR` → `home_dir/data/sessions/`
  - `DATABASE_URL` default → `sqlite:///home_dir/data/fleetent.db`
  - `im_gateway.access.APPROVALS_PATH` → `home_dir/data/im_approvals.json`
  - `observability.diagnostics._default_data_dir` → `home_dir/data/`
  - `observability.structured_logging` log directory → `home_dir/data/logs/` (default when
    `agent.observability.logging.directory` is unset or is the old relative `"data/logs"`)
- Update `AgentFile.observability.logging.directory` default to empty string; `agent_app`
  resolves it to `home_dir/data/logs/` when blank, so the log sink lands per-agent
- **BREAKING** (local only): existing `FLEETENT_HOME/data/` data is not migrated automatically;
  operators must move data manually or accept a clean-slate start per agent

## Capabilities

### New Capabilities

- `agent-data-isolation`: per-agent runtime data directory — `agents/<id>/data/` contains
  sessions, DB, logs, diagnostics and IM approvals for that agent exclusively

### Modified Capabilities

- `runtime-paths`: add `agent_data_dir(agent_id)` accessor to the central path resolver

## Impact

- `src/fleetent/paths.py` — new `agent_data_dir()` function
- `src/fleetent/runtime/agent_app.py` — data path redirection in `boot()`
- `src/fleetent/observability/structured_logging.py` — accept resolved absolute path
- `agents/default/agent.yaml.example` — update `observability.logging.directory` comment
- `tests/unit/` — new unit tests for path redirection logic
- `tests/integration/` — integration test verifying agent data lands in agent home
