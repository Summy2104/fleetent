# platform-control-plane Specification

## Purpose
The platform application is a pure control plane: admin/console + agent authoring +
start/stop control + health/auth. It boots with no agents and runs no IM connector,
agent loop, or sandbox — agent execution and IM ingress run only in an agent runtime
(`fleetent agent run`). Created by archiving change platform-control-plane.
## Requirements
### Requirement: Platform boots as a control plane with no agents

The platform application SHALL start successfully with no agent homes present and no IM
credentials configured. On boot it SHALL expose the admin/console + agent authoring +
start/stop control + health/auth, and SHALL NOT start any IM connector, agent loop, or
sandbox runtime.

#### Scenario: Empty platform boots

- **WHEN** the platform app starts with no agent home and no Slack/Telegram tokens
- **THEN** it serves `/health` and `/admin/*` without error and starts no IM connection

#### Scenario: Agent authoring still works

- **WHEN** an admin creates/edits an agent definition on the platform
- **THEN** the operation succeeds via the control-plane APIs (no agent execution required)

### Requirement: Agent execution endpoints are not on the platform

The platform application SHALL NOT serve `/chat`, `/ws`, or `/webhook/*`; agent execution
and IM ingress run only in an agent runtime process (`agent-runtime-cli`).

#### Scenario: Chat endpoint absent on the platform

- **WHEN** a client POSTs `/chat` to the platform app
- **THEN** the platform returns 404 (execution is served by an agent runtime, not the
  platform)

#### Scenario: No IM connector starts in the platform process

- **WHEN** the platform process is running
- **THEN** no Slack/Telegram connection is owned by it; IM is bound to agent runtimes

### Requirement: Platform server does not import agent runtime execution

`server.py` SHALL NOT import `fleetent.runtime.run_stream` or any other agent-loop execution
entry point. The admin console playground (`/admin/chat/*`) was the only path that required
this import; with playground removed, the platform process has no reason to execute an
agent loop in-process.

#### Scenario: Platform starts without runtime execution import

- **WHEN** the platform app starts
- **THEN** `server.py` does not import `run_stream` or any equivalent agent-loop callable from
  `fleetent.runtime`

#### Scenario: Admin console does not run agent turns in-process

- **WHEN** an admin uses the admin console
- **THEN** no agent loop turn is executed inside the platform process; agent execution remains
  exclusively in `fleetent agent run` processes
