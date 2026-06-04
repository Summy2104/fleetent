## Context

`server.py` is a monolith: platform admin/console + agent loop + IM connectors + /chat +
/ws + webhooks, all in one FastAPI lifespan. Agent definition is already file-driven
(single-file agent home), per-agent Slack connector and (with `per-agent-im-access`)
per-agent access are in place. What's missing is a way to run **one agent as its own
process** via the `fleetent` command (à la Hermes `hermes-agent` / `hermes gateway`).

## Goals / Non-Goals

**Goals**
- `fleetent agent run <home|name> [--port]` boots a single self-contained agent: loads
  its home, runs the loop, brings up its IM connectors (always), optionally serves
  HTTP/ws.
- `fleetent "<prompt>"` applies the deployed home agent (fix the current ignore-bug).
- IM is owned by the agent process; no platform dependency to run an agent.

**Non-Goals**
- Slimming the platform server (separate change `platform-control-plane`).
- Platform start/stop of agent processes (separate change `platform-agent-lifecycle`).
- A process supervisor/monitor (out of scope; platform only start/stops later).

## Decisions

### D1: A dedicated agent-runtime app, factored from server.py
Extract the agent/IM half of `server.py` into an agent-scoped runtime
(`fleetent.agent_runtime_app` or similar): a small ASGI app + a boot routine that scans
the single agent home, starts the per-agent Slack supervisor + Telegram (bound), starts
session/MCP/sandbox as needed, and (if `--port`) mounts `/chat` + `/ws`. No `/admin/*`.

### D2: `fleetent agent run` CLI + home layout
`fleetent` gains an `agent run <agent-id> [--port N]` subcommand. The multi-agent home
layout is **`FLEETENT_HOME/<agent-id>/`** (each agent its own subdir: `agent.yaml` +
`.env` + `data/`); `agent run <agent-id>` resolves and loads that home, then runs the
agent runtime in the foreground. IM always; HTTP/ws only with `--port`. (An explicit
`--home PATH` may override; the lone single-deploy `config/agent.yaml` mode stays for the
install.sh single-agent case.)

### D3: `fleetent "<prompt>"` applies the home agent
`run_sync` resolves the home/default agent via `agent_config` and applies its
`system_prompt`/`allowed_tools`/`allowed_skills` (today it uses the generic `_SYSTEM` and
no allowlist). One-shot CLI then behaves as the deployed agent.

### D4: IM bound to the agent
The agent runtime starts exactly its own agent's connectors (per-agent Slack supervisor
scoped to the one home agent; Telegram if the agent declares it). No IM runs without an
agent process.

## Risks / Trade-offs

- **Code extraction risk**: factoring agent/IM out of `server.py` is delicate → keep the
  monolith working during transition (both `uvicorn fleetent.server:app` and
  `fleetent agent run` can run); land platform-slim separately.
- **Sandbox in a per-agent process**: same Docker caveat as today (needs docker access);
  unchanged here.
- **Ports**: HTTP opt-in avoids multi-agent port clashes; document that two agents both
  using `--port` need distinct ports.

## Migration Plan

1. Factor an agent-runtime boot/app from `server.py`'s agent+IM parts (shared libs reused).
2. Add `fleetent agent run` CLI driving it.
3. Make `run_sync` apply the home agent.
4. Keep the platform monolith intact (slimming is the next change); add tests for the
   standalone runtime (loads home, IM bound, optional HTTP).

## Open Questions

- Transition overlap: before `platform-control-plane` lands, both the platform monolith
  and `fleetent agent run` could start the same agent's Slack connection (two Socket Mode
  sessions on one app). Not guarded here by decision (operators won't run both for the
  same agent); land `platform-control-plane` promptly after to remove the platform's IM.
