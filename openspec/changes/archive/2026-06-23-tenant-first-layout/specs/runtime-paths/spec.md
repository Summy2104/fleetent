## MODIFIED Requirements

### Requirement: Central path resolver

系统 SHALL 提供单一中心模块 `src/fleetent/paths.py` 解析 Platform home、租户目录、Agent home 与 runtime data 路径。业务模块的路径常量 SHALL 从该中心派生，不得各自读取家目录环境变量。

`config_dir()` SHALL NOT be a current deployment contract. Supported current config files live at Platform home root, `node/`, or under `tenants/<tenant>/agents/<agent>/`.

#### Scenario: Resolver module exists with platform and tenant-aware agent accessors
- **WHEN** 任一模块需要 Platform、tenant 或 Agent 路径
- **THEN** 存在 `src/fleetent/paths.py`
- **AND** 它导出 Platform home / management db / platform yaml accessors
- **AND** 它导出 tenant-aware accessors for `tenants/<tenant>/` and `tenants/<tenant>/agents/<agent>/`
- **AND** Agent home paths resolve under `tenants/<tenant>/agents/<agent>/`

#### Scenario: No scattered home env reads
- **WHEN** 审查业务模块的路径解析
- **THEN** `FLEETENT_HOME` 的读取只出现在 `paths.py` 一处
- **AND** 其它模块不直接读取家目录环境变量来定位 runtime paths

### Requirement: Home resolution precedence

路径解析 SHALL 按固定优先级确定 Platform home：显式 `FLEETENT_HOME` 环境变量 → 仓库本地 → 默认家目录 `~/.fleetent`。

#### Scenario: Explicit FLEETENT_HOME wins
- **WHEN** 环境变量 `FLEETENT_HOME` 已设置
- **THEN** Platform home 解析为该目录
- **AND** `platform_yaml_path()` 解析为 `$FLEETENT_HOME/platform.yaml`
- **AND** `management_db_path()` 解析为 `$FLEETENT_HOME/management.db`
- **AND** `tenant_agent_home_dir("acme", "bot")` 解析为 `$FLEETENT_HOME/tenants/acme/agents/bot`

#### Scenario: Repo-local used in development
- **WHEN** `FLEETENT_HOME` 未设置
- **AND** 当前工作目录检测到 fleetent 仓库标记
- **THEN** Platform home 解析为仓库根目录
- **AND** `platform_yaml_path()` 解析为 `./platform.yaml`
- **AND** `management_db_path()` 解析为 `./management.db`

#### Scenario: Home fallback when not in repo
- **WHEN** `FLEETENT_HOME` 未设置
- **AND** 当前工作目录未检测到仓库标记
- **THEN** Platform home 解析为 `~/.fleetent`
- **AND** `platform_yaml_path()` 解析为 `~/.fleetent/platform.yaml`
- **AND** `management_db_path()` 解析为 `~/.fleetent/management.db`

### Requirement: Development behavior unchanged

重定向后，仓库内运行的开发者入口 SHALL 保持零配置；但 canonical 管理库与 agent runtime 数据路径 SHALL 使用 tenant-first 目标态。

#### Scenario: Repo-run still uses local platform files
- **WHEN** 开发者在仓库根目录运行 `uv run fleetent` 或 `uv run pytest`，且未设置 `FLEETENT_HOME`
- **THEN** 应用读写 repo-root `.env` / `platform.yaml` / `management.db`
- **AND** 不依赖 `./config` 或 `~/.fleetent`

#### Scenario: Default database path uses root management db
- **WHEN** 仓库内运行且未覆盖 `DATABASE_URL`
- **THEN** 默认数据库定位到仓库根目录 `management.db`
- **AND** 不依赖 `data/management.db`

### Requirement: Per-agent data directory accessor

`paths.py` SHALL expose `tenant_agent_data_dir(tenant_id: str, agent_name: str) -> Path` returning `tenant_agent_home_dir(tenant_id, agent_name) / "data"`. Existing `agent_home_dir(name)` / `agent_data_dir(name)` MAY remain as default-tenant compatibility shims, but new managed/runtime code SHALL use tenant-aware accessors.

#### Scenario: tenant_agent_data_dir derives from tenant_agent_home_dir
- **WHEN** `paths.tenant_agent_data_dir("acme", "my-bot")` is called with `FLEETENT_HOME=/home/x/.fleetent`
- **THEN** it SHALL return `Path("/home/x/.fleetent/tenants/acme/agents/my-bot/data")`

#### Scenario: legacy agent_data_dir is default tenant shim
- **WHEN** `paths.agent_data_dir("my-bot")` is called for legacy compatibility
- **THEN** it SHALL resolve to `paths.tenant_agent_data_dir("default", "my-bot")`

#### Scenario: tenant-aware paths are injectable in tests
- **WHEN** a test monkeypatches `paths.base_dir` to return a `tmp_path`
- **THEN** `tenant_agent_home_dir("t", "a")` and `tenant_agent_data_dir("t", "a")` SHALL resolve under that `tmp_path`
