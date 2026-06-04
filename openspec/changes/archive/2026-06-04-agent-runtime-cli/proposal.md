## Why

An agent should run as a **self-contained process**, started by the `fleetent` command,
carrying its own loop + IM ingress + access control — independent of the platform. Today
the only way to run an agent is the monolithic `uvicorn fleetent.server:app` (platform +
all agents + IM in one process), and bare `fleetent "<prompt>"` ignores the deployed
`agent.yaml` entirely. This change introduces a standalone agent runtime launched via
`fleetent agent run`.

## What Changes

- **`fleetent agent run <home|name> [--port N]`**: start one agent as its own process —
  loads the agent home (`agent.yaml` + `.env` + local access), runs the agent loop, and
  **always** brings up its IM connectors (Slack/Telegram) bound to that agent. With
  `--port`, it also serves HTTP `/chat` + `/ws` (TUI) for that agent; without `--port`,
  it is IM/CLI/TUI-only (no HTTP). Foreground process.
- **Fix `fleetent "<prompt>"`**: the one-shot CLI SHALL apply the deployed home agent
  (its `system_prompt`/`allowed_tools`/`allowed_skills`), instead of the generic default
  it uses today.
- IM is **bound to the agent** (per point 3): the agent runtime owns its connectors;
  there is no IM outside an agent process.
- Reuses the runtime libs (loop, tools, skills, model, agent_config, session, IM
  adapters, per-agent slack supervisor) but as an **agent-scoped runtime**, not the
  platform app.

## Capabilities

### New Capabilities
- `agent-runtime-cli`: the `fleetent agent run` standalone agent runtime — loads one
  agent home, runs loop + bound IM + optional HTTP/ws, self-contained and platform-free.

### Modified Capabilities
- `file-agent-runtime`: the one-shot `fleetent "<prompt>"` path applies the resolved home
  agent's snapshot instead of the generic default.
- `im-gateway`: IM connectors run inside the agent runtime process (bound to the agent),
  driven by `fleetent agent run`, not only by the platform server lifespan.

## Impact

- **Code**: new agent-runtime entrypoint/app (factored out of `server.py`'s agent/IM
  parts) + `fleetent agent run` CLI; `run_sync` applies the home agent; the per-agent
  slack supervisor + telegram adapter started from the agent runtime.
- **Depends on** `per-agent-im-access` (the standalone agent enforces its own access).
- **Does not** yet slim the platform (that is `platform-control-plane`) — both run paths
  can coexist during transition.
- **Ports**: multi-agent on one host → HTTP is opt-in (`--port`); IM needs no port.
