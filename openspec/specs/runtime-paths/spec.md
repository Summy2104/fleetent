# runtime-paths Specification

## Purpose
定义运行时 config/data 路径的统一解析契约：所有路径常量从单一中心（`FLEETENT_HOME` → 仓库本地 → `~/.fleetent` 优先级）派生，使应用可运行在仓库外固定家目录，同时保持开发态零改动与路径常量的可注入性。
## Requirements
### Requirement: Central path resolver
系统 SHALL 提供单一中心模块 `src/fleetent/paths.py` 解析所有运行时 config 与 data 路径，业务模块的路径常量 SHALL 从该中心派生，不得各自读取家目录环境变量。

#### Scenario: Resolver module exists with config and data accessors
- **WHEN** 任一模块需要 config 或 data 路径
- **THEN** 存在 `src/fleetent/paths.py`
- **AND** 它导出 `config_dir()` 与 `data_dir()`
- **AND** 业务模块的路径常量从这两个函数派生

#### Scenario: No scattered home env reads
- **WHEN** 审查业务模块的路径解析
- **THEN** `FLEETENT_HOME` 的读取只出现在 `paths.py` 一处
- **AND** 其它模块不直接读取家目录环境变量来定位 config/data

### Requirement: Home resolution precedence
路径解析 SHALL 按固定优先级确定 base 目录：显式 `FLEETENT_HOME` 环境变量 → 仓库本地 → 默认家目录 `~/.fleetent`。

#### Scenario: Explicit FLEETENT_HOME wins
- **WHEN** 环境变量 `FLEETENT_HOME` 已设置
- **THEN** `config_dir()` 解析为 `$FLEETENT_HOME/config`
- **AND** `data_dir()` 解析为 `$FLEETENT_HOME/data`

#### Scenario: Repo-local used in development
- **WHEN** `FLEETENT_HOME` 未设置
- **AND** 当前工作目录检测到 fleetent 仓库标记（`pyproject.toml` 含 `name = "fleetent"` 或存在 `./config`）
- **THEN** `config_dir()` 解析为仓库本地 `./config`
- **AND** `data_dir()` 解析为仓库本地 `./data`

#### Scenario: Home fallback when not in repo
- **WHEN** `FLEETENT_HOME` 未设置
- **AND** 当前工作目录未检测到仓库标记
- **THEN** `config_dir()` 解析为 `~/.fleetent/config`
- **AND** `data_dir()` 解析为 `~/.fleetent/data`

#### Scenario: Explicit home overrides repo-local
- **WHEN** 在 fleetent 仓库内运行
- **AND** 同时设置了 `FLEETENT_HOME`
- **THEN** 解析使用 `FLEETENT_HOME`，而非仓库本地

### Requirement: Development behavior unchanged
重定向后，仓库内运行的既有行为 SHALL 保持不变，开发者无需设置任何环境变量。

#### Scenario: Repo-run still uses local config and data
- **WHEN** 开发者在仓库根目录运行 `uv run fleetent` 或 `uv run pytest`，且未设置 `FLEETENT_HOME`
- **THEN** 应用读写 `./config` 与 `./data`
- **AND** 不依赖 `~/.fleetent`

#### Scenario: Default database path preserved in repo
- **WHEN** 仓库内运行且未覆盖 `DATABASE_URL`
- **THEN** 默认数据库定位到仓库本地 `data/` 下，文件名与重定向前一致（不改名）

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

