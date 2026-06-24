## ADDED Requirements

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
