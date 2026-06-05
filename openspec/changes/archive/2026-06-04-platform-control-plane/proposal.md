## Why

The platform should be a **control plane**: it manages (creates/edits) multiple agents
and can start/stop them, but it does not itself run agents or hold IM. Today
`fleetent.server:app` bundles the control plane with the agent loop, IM connectors,
`/chat`, `/ws`, and webhooks — so the platform can't start "empty" and agent execution is
welded to the platform. With the standalone agent runtime in place (`agent-runtime-cli`),
this change **slims the platform app to control-plane only**.

## What Changes

- **Remove agent-execution + IM from the platform app**: `/chat`, `/ws` (TUI),
  `/webhook/*`, the IM connector manager + per-agent Slack supervisor, the agent loop,
  and sandbox bring-up move out of the platform lifespan (they live in the agent runtime).
- **Platform starts with zero agents**: the platform boots cleanly with no agent homes
  present; agent CRUD/console and start/stop control remain.
- **Platform keeps**: `/admin/*` (user/skill/provider/kb/connector/stats/monitor/agent
  console + agent authoring), health, auth, cron for platform-level jobs.
- **BREAKING**: hitting `/chat`/`/ws` on the platform is gone — those are served by an
  agent runtime process (optionally, via `fleetent agent run --port`).

## Capabilities

### New Capabilities
- `platform-control-plane`: the platform app is a control plane — admin/console + agent
  authoring + start/stop control, starting cleanly with no agents and running no IM/loop.

### Modified Capabilities
- `im-gateway`: IM ingress no longer runs in the platform process; it runs only inside an
  agent runtime (`agent-runtime-cli`).
- `configuration`: the platform process requires no agent home / IM credentials to boot;
  agent-scoped config/secrets belong to agent homes.

## Impact

- **Code**: `server.py` lifespan + routes pruned to control-plane (drop chat/ws/webhook/
  IM/loop/sandbox bring-up); those move to / stay in the agent runtime.
- **Depends on** `agent-runtime-cli` (the moved-out execution path must exist first).
- **Enables** `platform-agent-lifecycle` (platform then materializes homes + start/stops
  agent processes).
- **Tests**: platform boot-with-no-agents; removed endpoints return 404 on the platform;
  agent execution covered by the agent-runtime suite.
