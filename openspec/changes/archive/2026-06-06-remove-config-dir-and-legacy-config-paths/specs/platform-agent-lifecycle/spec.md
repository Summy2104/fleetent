## MODIFIED Requirements

### Requirement: Create/update materializes a runnable agent home

When the platform creates or updates an agent, it SHALL materialize that agent's
self-contained home under `FLEETENT_HOME/agents/<agent-id>/`: an `agent.yaml`
(definition + `connectors` + per-agent `access` block), a `.env` scaffold, and `data/`,
so the agent is runnable by `fleetent agent run`.

#### Scenario: Create writes the home
- **WHEN** an admin creates agent `support` on the platform
- **THEN** `FLEETENT_HOME/agents/support/agent.yaml` is written from the authored definition
- **AND** `FLEETENT_HOME/agents/support/.env` is present, with secrets referenced only by env-var name
- **AND** `FLEETENT_HOME/agents/support/data/` exists

#### Scenario: Update re-materializes
- **WHEN** an admin edits `support`'s definition
- **THEN** `FLEETENT_HOME/agents/support/agent.yaml` is rewritten to match
- **AND** operator-provided `.env` secret values are preserved

### Requirement: Agent materialization writes self-contained Agent homes

平台 materialize SHALL 将每个 Agent 写成 self-contained Agent home under
`agents/<agent-id>/`. 该 home SHALL 包含 `agent.yaml`, `.env`, and `data/`; runtime SHALL be
able to run from that home without Platform DB access. Platform-owned config files such as
`platform.yaml` and embedded Knowledge construction files SHALL NOT be written into Agent homes.

#### Scenario: Materialize writes Agent home
- **WHEN** 平台部署 Agent `support`
- **THEN** materialize 写入 `agents/support/agent.yaml`
- **AND** 写入或保留 `agents/support/.env`
- **AND** 确保 `agents/support/data/` 存在

#### Scenario: Old flat deploy path is not written
- **WHEN** 平台部署 Agent `support`
- **THEN** 不写入 `support/agent.yaml`
- **AND** 不写入 Platform home root `agent.yaml`

#### Scenario: Knowledge binding export only
- **WHEN** 一个 agent 绑定了 KB
- **THEN** 生成的 `agent.yaml` 含 `knowledge.bindings`
- **AND** 不含 Google Drive / Confluence source construction details
- **AND** materialize 不写 `config/knowledge.yaml`
