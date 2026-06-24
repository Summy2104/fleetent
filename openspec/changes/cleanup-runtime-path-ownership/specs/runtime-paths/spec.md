## MODIFIED Requirements

### Requirement: Central path resolver

系统 SHALL 提供单一中心模块 `src/fleetent/paths.py` 解析 Platform home、平台级宿主产物目录、租户目录、Agent home 与 Agent runtime data 路径。业务模块的路径常量 SHALL 从该中心或 agent runtime 注入的语义化 sink 派生，不得各自读取家目录环境变量。

`config_dir()` SHALL NOT be a current deployment contract. Supported current config files live at Platform home root, `node/`, or under `tenants/<tenant>/agents/<agent>/`.

#### Scenario: Resolver module exists with platform and tenant-aware agent accessors
- **WHEN** 任一模块需要 Platform、tenant 或 Agent 路径
- **THEN** 存在 `src/fleetent/paths.py`
- **AND** 它导出 Platform home / management db / platform yaml / platform logs / platform diagnostics accessors
- **AND** 它导出 tenant-aware accessors for `tenants/<tenant>/` and `tenants/<tenant>/agents/<agent>/`
- **AND** Agent home paths resolve under `tenants/<tenant>/agents/<agent>/`

#### Scenario: No scattered home env reads
- **WHEN** 审查业务模块的路径解析
- **THEN** `FLEETENT_HOME` 的读取只出现在 `paths.py`、node config bootstrap 或显式 CLI/provision 边界
- **AND** 其它模块不直接读取家目录环境变量来定位 runtime paths

### Requirement: Home-level path ownership

`FLEETENT_HOME` 根目录 SHALL 只默认承载跨租户控制面和宿主级产物：`management.db`、`platform.yaml`、平台 `.env`、dev-only `.dev_secret_key`、`node/`、`logs/`、`diagnostics/`、`tenants/`。系统默认路径 SHALL NOT 使用 `FLEETENT_HOME/data/` 承载 platform 或 agent runtime 产物。

#### Scenario: Platform logs are root-level
- **WHEN** `paths.logs_dir()` is called with `FLEETENT_HOME=/home/x/.fleetent`
- **THEN** it SHALL return `/home/x/.fleetent/logs`
- **AND** it SHALL NOT return `/home/x/.fleetent/data/logs`

#### Scenario: Platform diagnostics are root-level
- **WHEN** `paths.diagnostics_dir()` is called with `FLEETENT_HOME=/home/x/.fleetent`
- **THEN** it SHALL return `/home/x/.fleetent/diagnostics`
- **AND** it SHALL NOT return `/home/x/.fleetent/data/diagnostics`

#### Scenario: Management DB remains root-level
- **WHEN** `paths.management_db_path()` is called with `FLEETENT_HOME=/home/x/.fleetent`
- **THEN** it SHALL return `/home/x/.fleetent/management.db`
- **AND** the system SHALL NOT move it under `platform/` or `data/`

#### Scenario: Global data is not a canonical write root
- **WHEN** fresh dev home bootstrap and one managed agent boot complete
- **THEN** `FLEETENT_HOME/data/` SHALL NOT contain `traces.jsonl`, `sessions/`, `workspaces/`, `tool_spillover/`, `sandbox_output/`, `diagnostics/`, `im_approvals.json`, or SQLite runtime databases

### Requirement: Per-agent runtime data ownership

All agent runtime files SHALL be scoped under `<agent-home>/data/` unless they are explicit home inputs (`agent.yaml`, `.env`, `skills/`) or process metadata (`.fleetent.pid`, `exchange/`). This includes session JSON files, legacy JSONL traces while present, agent logs, diagnostics exports, IM approval state, workspace directories, tool spillover files, sandbox output spill files, and agent-side SQLite files.

#### Scenario: Agent runtime data sinks are under agent home data
- **WHEN** agent `support` in tenant `acme` runs with home `FLEETENT_HOME/tenants/acme/agents/support`
- **THEN** runtime data writes target `FLEETENT_HOME/tenants/acme/agents/support/data/`
- **AND** no agent runtime write targets `FLEETENT_HOME/data/`

#### Scenario: Tenant resources remain tenant-level
- **WHEN** tenant `acme` KB resources are opened
- **THEN** KB relation and vector files resolve under `FLEETENT_HOME/tenants/acme/`
- **AND** they do not resolve under `FLEETENT_HOME/data/` or an agent `data/` directory
