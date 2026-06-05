## Context

`platform-control-plane` makes the platform a control plane; `agent-runtime-cli` provides
`fleetent agent run`; `per-agent-im-access` defines the per-agent access materialized
into the home. This change connects them: platform creates a runnable agent home and can
start/stop the agent process — lightweight, no monitoring (user-chosen).

## Goals / Non-Goals

**Goals**
- Platform "create/update agent" materializes the agent's home (`agent.yaml` + `.env`
  scaffold + per-agent access) so it is runnable by `fleetent agent run`.
- Platform can start an agent (spawn `fleetent agent run <name>`) and stop it (terminate
  the tracked process).

**Non-Goals**
- Health monitoring, auto-restart, or supervision of agent processes (explicitly out:
  "能启动和停掉即可，不监控").
- Remote/multi-host orchestration (single-host process spawn here).

## Decisions

### D1: Materialize the home on create/update
On agent create/update, the platform writes `FLEETENT_HOME/<agent-id>/agent.yaml` (from the
authored definition: prompt/tools/skills/mcp/connectors + the per-agent `access` block)
and seeds a `.env` scaffold (env-var names only; operator fills secrets). This is the
DB→file export contract.

### D2: Start = spawn `fleetent agent run`, Stop = terminate
A start/stop controller spawns `fleetent agent run <name>` as a subprocess and records
its PID; stop terminates it. The controller tracks "started-by-us" PIDs only. No probe,
no restart loop, no heartbeat — a dead agent stays dead until started again.

### D3: Admin endpoints
`POST /admin/agents/<name>/start` → materialize-if-needed + spawn; `/stop` → terminate;
status reflects only "tracked-running vs not" (no deep health).

## Risks / Trade-offs

- **No monitoring** → operators see no auto-recovery; intentional per the chosen model.
  Status is shallow (tracked PID alive), not real health.
- **Secrets**: `.env` is scaffolded with env-var names only; real secrets are placed by
  the operator into the agent home (never materialized as plaintext by the platform).
- **PID tracking across platform restarts**: if the platform restarts, tracked PIDs may
  be lost → document that start/stop tracking is best-effort within a platform lifetime.

## Migration Plan

1. Land `per-agent-im-access`, `agent-runtime-cli`, `platform-control-plane` first.
2. Add home materialization to agent create/update.
3. Add the start/stop controller (spawn/terminate `fleetent agent run`, PID tracking).
4. Add admin start/stop endpoints + shallow status; tests for materialize + spawn + stop.

## Open Questions

- Persisting tracked PIDs across platform restarts (file vs in-memory) — in-memory is
  simplest given "no monitoring"; revisit if operators need restart-survival.
