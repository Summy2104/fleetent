## Context

After `agent-runtime-cli`, agent execution + IM live in a standalone `fleetent agent run`
process. The platform monolith (`server.py`) still also runs them. This change removes
that duplication from the platform so it is a pure control plane that can start empty.

## Goals / Non-Goals

**Goals**
- Platform app = `/admin/*` + agent authoring/console + start/stop control + health/auth.
- Platform boots with no agent homes and no IM credentials.
- No `/chat`, `/ws`, `/webhook`, IM connectors, agent loop, or sandbox bring-up in the
  platform process.

**Non-Goals**
- The start/stop spawning + home materialization mechanics (that is
  `platform-agent-lifecycle`).
- Removing shared libraries (the agent runtime still uses them).

## Decisions

### D1: Prune the platform lifespan + routes
Remove from `server.py`: `_connector_manager.start_all_enabled`,
`_slack_supervisor.start_from_index`, MCP register/health for agent use, sandbox probe,
session maintenance, and the `/chat`, `/ws`, `/webhook` routes. Keep admin routers,
health, auth, builtin-admin seed, and platform-level cron.

### D2: Platform boots agent-free
The platform no longer scans an agent home or requires IM tokens. `agent_config` is used
by the platform only for **authoring/reading** definitions (CRUD), not for running.

### D3: Execution path is the agent runtime
Anything removed here is already (or concurrently) provided by `agent-runtime-cli`. The
two are complementary: platform authors/controls; agent runtime executes.

## Risks / Trade-offs

- **Removing live endpoints is breaking** for anything that POSTed `/chat` to the
  platform → callers move to an agent runtime (`--port`) or the platform proxies later
  (out of scope). Document the break.
- **Test churn**: many server tests assume the monolith → split into platform-app tests
  (control-plane) and agent-runtime tests (execution). Migrate accordingly.
- **Ordering**: must land after `agent-runtime-cli` so execution isn't lost in the gap.

## Migration Plan

1. Land `agent-runtime-cli` first.
2. Prune the platform lifespan + routes to control-plane.
3. Migrate server tests: platform-side keeps admin/health; execution tests move to the
   agent-runtime suite.
4. Verify platform boots with no agent home / no IM tokens.

## Open Questions

- Whether the platform should later offer a thin `/chat` proxy to a running agent
  (convenience) — deferred; not in this change.
