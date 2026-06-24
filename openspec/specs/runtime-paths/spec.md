# runtime-paths Specification

## Purpose
定义运行时 config/data 路径的统一解析契约：所有路径常量从单一中心（`FLEETENT_HOME` → 仓库本地 → `~/.fleetent` 优先级）派生，使应用可运行在仓库外固定家目录，同时保持开发态零改动与路径常量的可注入性。
## Requirements
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

### Requirement: Path constant injectability
重定向后，业务模块的路径常量 SHALL 仍可通过 `monkeypatch` 注入以隔离测试，且整体 home 重定向 SHALL 可通过环境变量实现。

#### Scenario: Module-level constant still patchable
- **WHEN** 测试 `monkeypatch.setattr` 某模块的路径常量到临时目录
- **THEN** 该模块的读写命中临时目录
- **AND** 不触碰真实 `data/` 或用户家目录

#### Scenario: Whole-home redirect via env in tests
- **WHEN** 测试 `monkeypatch.setenv("FLEETENT_HOME", tmp_path)` 并触发路径重解析
- **THEN** config 与 data 整体重定向到 `tmp_path` 下
- **AND** 不触碰真实 `data/` 或用户家目录

### Requirement: DATABASE_URL bypass consolidation
直接拼接 `sqlite:///data/...` 的旁路读取 SHALL 收编为经中心解析，但 SHALL 保持 `DATABASE_URL` 环境变量的优先级与默认值语义不变。

#### Scenario: DATABASE_URL still takes precedence
- **WHEN** 环境变量 `DATABASE_URL` 已设置
- **THEN** 数据库定位使用该 URL，优先于 `paths.py` 派生的默认值

#### Scenario: Default DB derives from resolved data dir
- **WHEN** `DATABASE_URL` 未设置
- **THEN** 默认数据库路径从 `data_dir()` 派生
- **AND** 不再出现绕过中心解析、直接硬编码 `sqlite:///data/...` 的读取点

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

