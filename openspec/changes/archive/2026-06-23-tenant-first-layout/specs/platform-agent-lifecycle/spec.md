## MODIFIED Requirements

### Requirement: Create/update materializes a runnable agent home

When the platform creates or updates a managed agent, it SHALL update the management database and make a new desired-state payload available to the owning node. Platform SHALL NOT write the managed agent's real home directly. The owning node SHALL materialize the runnable home under `FLEETENT_HOME/tenants/<tenant>/agents/<agent>/`.

#### Scenario: Create exposes desired state
- **WHEN** an admin creates managed agent `support` on the platform
- **THEN** platform persists the authored definition in management DB
- **AND** `GET /nodes/{node-id}/desired-state` includes `support` for its placement
- **AND** platform does not write `tenants/<tenant>/agents/support/agent.yaml` itself

#### Scenario: Update changes desired state
- **WHEN** an admin edits `support`'s definition
- **THEN** platform updates the management DB source of truth
- **AND** the next desired-state response contains the updated agent config
- **AND** the owning node is responsible for rewriting the home and restarting if needed

### Requirement: Agent materialization writes self-contained Agent homes

Managed Agent homes SHALL be self-contained under `tenants/<tenant>/agents/<agent>/`, but in managed mode the writer SHALL be node reconcile. Platform-owned config files such as `platform.yaml` and embedded Knowledge construction files SHALL NOT be written into Agent homes.

#### Scenario: Node materializes Agent home
- **WHEN** node reconciles desired agent `support` in tenant `acme`
- **THEN** node writes `tenants/acme/agents/support/agent.yaml`
- **AND** writes or preserves `tenants/acme/agents/support/.env`
- **AND** ensures `tenants/acme/agents/support/data/` exists

#### Scenario: Platform managed path does not write home
- **WHEN** platform creates, updates, clones, or applies a managed agent definition
- **THEN** platform does not write `agent.yaml`, `.env`, `skills/`, or `data/` under that agent's home

#### Scenario: Knowledge binding export only
- **WHEN** 一个 agent 绑定了 KB
- **THEN** desired-state 中的 agent config 含 `knowledge.bindings`
- **AND** 不含 Google Drive / Confluence source construction details
- **AND** platform 不写 standalone Knowledge YAML 到 agent home

### Requirement: Materialize 将平台 skill 文件分发到 agent home

平台 SHALL NOT 直接将 skill 文件分发到 managed agent home。平台 SHALL 在 desired-state 中提供 skill manifest 与 bundle URL；node SHALL 下载 bundle 并部署到 agent home 的 `skills/` 目录。standalone/local helper MAY copy skills locally, but it is not the managed production path.

#### Scenario: Platform desired state references skill bundles
- **WHEN** agent `support` 启用 skill `foo`
- **THEN** desired-state 包含 `foo` 的 `base_version`、`base_commit`、`bundle_url` 与 `bundle_sha256`
- **AND** platform 不 copy `foo` 到 managed agent home

#### Scenario: Node deploys skill files
- **WHEN** node reconcile 看到本地缺少 desired skill `foo` 的 `base_version`
- **THEN** node 下载 bundle
- **AND** 解压部署到 `tenants/<tenant>/agents/<agent>/skills/foo/`
