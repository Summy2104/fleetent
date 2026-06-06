## MODIFIED Requirements

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
