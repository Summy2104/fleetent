## MODIFIED Requirements

### Requirement: Central path resolver

系统 SHALL 提供单一中心模块 `src/fleetent/paths.py` 解析 Platform home、Agent home 与 data 路径。
业务模块的路径常量 SHALL 从该中心派生，不得各自读取家目录环境变量。

`config_dir()` SHALL NOT be a current deployment contract. Supported current config files live at
Platform home root or under `agents/<agent-id>/`.

#### Scenario: Resolver module exists with platform and agent accessors
- **WHEN** 任一模块需要 Platform 或 Agent 路径
- **THEN** 存在 `src/fleetent/paths.py`
- **AND** 它导出 Platform home / data / platform yaml accessors
- **AND** Agent home paths resolve under `agents/<agent-id>/`

#### Scenario: No scattered home env reads
- **WHEN** 审查业务模块的路径解析
- **THEN** `FLEETENT_HOME` 的读取只出现在 `paths.py` 一处
- **AND** 其它模块不直接读取家目录环境变量来定位 runtime paths

### Requirement: Home resolution precedence

路径解析 SHALL 按固定优先级确定 Platform home：显式 `FLEETENT_HOME` 环境变量 → 仓库本地 → 默认家目录
`~/.fleetent`。

#### Scenario: Explicit FLEETENT_HOME wins
- **WHEN** 环境变量 `FLEETENT_HOME` 已设置
- **THEN** Platform home 解析为该目录
- **AND** `platform_yaml_path()` 解析为 `$FLEETENT_HOME/platform.yaml`
- **AND** `data_dir()` 解析为 `$FLEETENT_HOME/data`

#### Scenario: Repo-local used in development
- **WHEN** `FLEETENT_HOME` 未设置
- **AND** 当前工作目录检测到 fleetent 仓库标记
- **THEN** Platform home 解析为仓库根目录
- **AND** `platform_yaml_path()` 解析为 `./platform.yaml`
- **AND** `data_dir()` 解析为 `./data`

#### Scenario: Home fallback when not in repo
- **WHEN** `FLEETENT_HOME` 未设置
- **AND** 当前工作目录未检测到仓库标记
- **THEN** Platform home 解析为 `~/.fleetent`
- **AND** `platform_yaml_path()` 解析为 `~/.fleetent/platform.yaml`
- **AND** `data_dir()` 解析为 `~/.fleetent/data`

### Requirement: Development behavior unchanged

重定向后，仓库内运行的既有行为 SHALL 保持不变，开发者无需设置任何环境变量。

#### Scenario: Repo-run still uses local platform files and data
- **WHEN** 开发者在仓库根目录运行 `uv run fleetent` 或 `uv run pytest`，且未设置 `FLEETENT_HOME`
- **THEN** 应用读写 repo-root `.env` / `platform.yaml` and `./data`
- **AND** 不依赖 `./config` 或 `~/.fleetent`

#### Scenario: Default database path preserved in repo
- **WHEN** 仓库内运行且未覆盖 `DATABASE_URL`
- **THEN** 默认数据库定位到仓库本地 `data/` 下
- **AND** 不依赖 `config/`
