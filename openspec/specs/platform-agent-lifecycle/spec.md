# platform-agent-lifecycle Specification

## Purpose
Platform-side agent lifecycle: creating/updating an agent materializes its runnable
self-contained home, and the platform can start/stop the agent as a `fleetent agent run`
process without monitoring it. Created by archiving change platform-agent-lifecycle.
## Requirements
### Requirement: Create/update materializes a runnable agent home

When the platform creates or updates an agent, it SHALL materialize that agent's
self-contained home: an `agent.yaml` (definition + `connectors` + per-agent `access`
block) and a `.env` scaffold (env-var names only, no plaintext secrets), under the
agent's home directory, so the agent is runnable by `fleetent agent run`.

#### Scenario: Create writes the home

- **WHEN** an admin creates agent `support` on the platform
- **THEN** `FLEETENT_HOME/support/agent.yaml` is written from the authored definition and
  a `.env` scaffold is present, with secrets referenced only by env-var name

#### Scenario: Update re-materializes

- **WHEN** an admin edits `support`'s definition
- **THEN** its home `agent.yaml` is rewritten to match, leaving operator-provided `.env`
  secret values intact

### Requirement: Start and stop agent processes without monitoring

The platform SHALL be able to start an agent by spawning `fleetent agent run <name>` as a
subprocess and to stop it by terminating the tracked process. The platform SHALL track
started PIDs to stop them, and SHALL NOT health-monitor, auto-restart, or supervise the
agent processes.

#### Scenario: Start spawns the agent runtime

- **WHEN** `POST /admin/agents/support/start` is called
- **THEN** the platform spawns `fleetent agent run support` (materializing the home first
  if needed) and records the process

#### Scenario: Stop terminates the tracked process

- **WHEN** `POST /admin/agents/support/stop` is called for a started agent
- **THEN** the platform terminates that tracked process

#### Scenario: No supervision

- **WHEN** a started agent process exits on its own
- **THEN** the platform does not restart it and reports it as not-running; recovery
  requires an explicit start

### Requirement: Agent materialization writes self-contained Agent homes

平台 materialize SHALL 将每个 Agent 写成 self-contained Agent home。该 home SHALL 包含 `agent.yaml`,
`.env`, and `data/`; runtime SHALL be able to run from that home without Platform DB access.

#### Scenario: Materialize writes Agent home
- **WHEN** 平台部署 Agent `support`
- **THEN** materialize 写入 `agents/support/agent.yaml`
- **AND** 写入或保留 `agents/support/.env`
- **AND** 确保 `agents/support/data/` 存在

#### Scenario: Platform env does not leak into Agent home
- **WHEN** materialize 写入 Agent `.env`
- **THEN** `.env` 只含该 Agent required env
- **AND** 不含 `FLEETENT_SECRET_KEY` 或平台 DB 变量

