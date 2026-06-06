## MODIFIED Requirements

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

#### Scenario: Platform env does not leak into Agent home
- **WHEN** materialize 写入 Agent `.env`
- **THEN** `.env` 只含该 Agent required env
- **AND** 不含 `FLEETENT_SECRET_KEY`、`DATABASE_URL` 或 Platform-owned KB construction env

#### Scenario: Knowledge binding export only
- **WHEN** 一个 agent 绑定了 KB
- **THEN** 生成的 `agent.yaml` 含 `knowledge.bindings`
- **AND** 不含 Google Drive / Confluence source construction details
- **AND** materialize 不写 `config/knowledge.yaml`
