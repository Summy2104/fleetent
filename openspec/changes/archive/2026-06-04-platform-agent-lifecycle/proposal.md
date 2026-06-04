## Why

With a control-plane platform (`platform-control-plane`) and a standalone agent runtime
(`agent-runtime-cli`), the platform needs to actually **create** agents (materialize a
runnable home) and **start/stop** them as processes. The user-chosen control model is
lightweight: the platform can launch and terminate agent processes, but does NOT monitor
or supervise them.

## What Changes

- **Create agent → materialize home**: the platform "create/update agent" operation
  writes the agent's self-contained home — `agent.yaml` (definition + `connectors` +
  `access` block) and `.env` scaffold — to that agent's home directory. This is the
  DB→file export contract: platform authors, agent home holds.
- **Start/stop agent processes (no monitoring)**: the platform can start an agent by
  spawning `fleetent agent run <name>` as a subprocess, and stop it by terminating that
  process. It tracks the started PIDs to stop them; it does NOT health-check, restart, or
  supervise.
- **Admin endpoints**: `POST /admin/agents/<name>/start` and `/stop` (and a status that
  only reflects "started by us / not", not deep monitoring).

## Capabilities

### New Capabilities
- `platform-agent-lifecycle`: platform-side creation that materializes a runnable agent
  home, plus start/stop of agent processes via `fleetent agent run` without monitoring.

### Modified Capabilities
- `agent-definition`: creating/updating an agent additionally materializes its home
  (`agent.yaml` + `.env` + per-agent access) for the standalone runtime.
- `install-bootstrap`: deployment layout/bootstrap accounts for platform-materialized
  agent homes (flat home per agent), consistent with the single-file agent model.

## Impact

- **Code**: platform agent-create writes the home (reusing the agent home schema +
  per-agent access materialization from `per-agent-im-access`); a start/stop controller
  that spawns/terminates `fleetent agent run` subprocesses and records PIDs; admin
  start/stop endpoints.
- **Depends on** `agent-runtime-cli` (the command to spawn), `platform-control-plane`
  (the slim platform host), and `per-agent-im-access` (access materialization).
- **No supervision**: a crashed agent stays down until started again (by design).
- **Tests**: create→home materialized on disk; start spawns the expected command; stop
  terminates the tracked process; no restart/monitor.
