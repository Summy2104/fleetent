# runtime-paths Specification

## Purpose
定义运行时 config/data 路径的统一解析契约：所有路径常量从单一中心（`FLEETENT_HOME` → 仓库本地 → `~/.fleetent` 优先级）派生，使应用可运行在仓库外固定家目录，同时保持开发态零改动与路径常量的可注入性。
## Requirements
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

`paths.py` SHALL expose `agent_data_dir(agent_id: str) -> Path` returning
`agents_dir() / agent_id / "data"`. This formalises the per-agent data root so callers
never construct it inline and the derivation is testable in isolation.

#### Scenario: agent_data_dir derives from agents_dir

- **WHEN** `paths.agent_data_dir("my-bot")` is called with `FLEETENT_HOME=/home/x/.fleetent`
- **THEN** it SHALL return `Path("/home/x/.fleetent/agents/my-bot/data")`

#### Scenario: agent_data_dir is injectable in tests

- **WHEN** a test monkeypatches `paths.agents_dir` to return a `tmp_path`
- **THEN** `paths.agent_data_dir("test-agent")` SHALL return `tmp_path / "test-agent" / "data"`

