## ADDED Requirements

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
