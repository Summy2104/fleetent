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

### Requirement: 平台裸启动不依赖 agent 侧 state_db

`uvicorn fleetent.server:app` SHALL 能在干净环境裸启动成功(lifespan 跑完、`/health` 可达),SHALL NOT 依赖 agent 侧 `state_db` 被初始化。平台 lifespan SHALL NOT 执行 agent 侧的 approval reconcile(`reconcile_expired_approvals`)等需要 per-agent `state_db` 的操作——这类操作归 agent 进程 boot(approval 是 agent 侧数据)。

#### Scenario: 平台裸启动成功

- **WHEN** 在未 `set_state_db` 的干净进程里 `uvicorn fleetent.server:app` 启动
- **THEN** lifespan 跑完、`/health` 返回 200,**不抛 `approval_store: state_db not initialized`**

#### Scenario: agent 侧 reconcile 不在平台 lifespan

- **WHEN** 检视平台 lifespan
- **THEN** 不调用 `reconcile_expired_approvals` 等读 per-agent `approval_store` 的操作;过期审批清理由 agent 进程 boot(state_db 已接处)承担

### Requirement: Platform does not write agent homes

The platform application SHALL NOT provide any HTTP or CLI endpoint that writes an agent
home or its materialized contents (`agent.yaml`, `.env`, `skills/`) to disk. Agent-home
materialization has exactly one owner per deployment mode: **managed** → the node supervisor's
reconcile loop (`fleetent node start`); **standalone** → the CLI scaffold (`fleetent agent init`).
The platform MAY expose **read-only** projections of an agent's intended config (e.g. returning
the rendered `agent.yaml` text in an HTTP response body) since these do not write a home.

#### Scenario: No platform endpoint writes an agent home

- **WHEN** a client inspects the platform's HTTP API and CLI surface
- **THEN** there SHALL be no endpoint that writes `agent.yaml` / `.env` / `skills/` into an
  agent home directory (e.g. the removed `POST /admin/agents/{name}/deploy`)
- **AND** agent-home materialization happens only via node reconcile (managed) or
  `fleetent agent init` (standalone)

#### Scenario: Read-only config projection is allowed

- **WHEN** a client requests an agent's rendered config (e.g. `GET /admin/agents/{name}/agent-yaml`)
- **THEN** the platform MAY return the rendered `agent.yaml` text in the response body
- **AND** it MUST NOT write that text to any agent home on disk

