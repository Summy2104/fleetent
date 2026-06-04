# install-bootstrap Specification

## Purpose
定义单机一键安装契约：从干净的 Linux/macOS/WSL2 环境 bootstrap 出全局可用、与工作目录解耦的 fleetent（uv tool 安装三入口 + `FLEETENT_HOME` 固定状态目录 + 配置模板 + Alembic 初始化数据库），幂等可重入，提供非交互 flags，并对缺失的可选依赖（Docker）给出非阻断告警。面向开发者/单机快速体验，与 Docker 生产部署互补。
## Requirements
### Requirement: Install script entry point
系统 SHALL 提供 `scripts/install.sh` 作为单机一键安装入口，从干净的 Linux/macOS/WSL2 环境 bootstrap 出可运行的 fleetent。

#### Scenario: Install script exists and is executable
- **WHEN** operator 查看仓库 scripts
- **THEN** 存在 `scripts/install.sh`
- **AND** 该文件具有可执行权限

#### Scenario: Help flag prints usage and exits
- **WHEN** operator 运行 `scripts/install.sh --help`
- **THEN** script 打印用法说明（含所有受支持的 flag）
- **AND** 以退出码 0 退出
- **AND** 不修改任何文件、不安装任何依赖

### Requirement: Environment hygiene
install script SHALL 在执行任何安装步骤前净化继承的 Python 环境变量，避免从调用方继承的路径遮蔽本仓库的模块导入。

#### Scenario: Inherited PYTHONPATH is cleared
- **WHEN** operator 在已设置 `PYTHONPATH` 的 shell 中运行 install script
- **THEN** script 在安装步骤执行前 unset `PYTHONPATH`
- **AND** unset `PYTHONHOME`

#### Scenario: Fail-fast on error
- **WHEN** 任一安装步骤返回非零退出码
- **THEN** script 立即停止（`set -e`）
- **AND** 不继续后续步骤

### Requirement: uv runtime provisioning
install script SHALL 探测 uv 是否已存在，仅在缺失时安装，并用 uv 管理 Python 3.12 运行时。

#### Scenario: Existing uv is reused
- **WHEN** uv 已存在于 `PATH`、`~/.local/bin` 或 `~/.cargo/bin`
- **THEN** script 复用已有 uv，不重复安装

#### Scenario: uv installed when missing
- **WHEN** 上述位置均找不到 uv
- **THEN** script 安装 uv 后再继续

#### Scenario: Python version verified
- **WHEN** script 校验运行时
- **THEN** 确认可用 Python 版本满足 `>=3.12`
- **AND** 不满足时 fail fast 并提示所需版本

### Requirement: Global command installation
install script SHALL 用 `uv tool install` 把 `fleetent`、`fleetent-admin`、`fleetent-tui` 安装为可在任意目录调用的全局命令。

#### Scenario: Three entry points available globally
- **WHEN** 安装完成
- **THEN** `fleetent`、`fleetent-admin`、`fleetent-tui` 三个 console-script 入口链接到 `~/.local/bin`
- **AND** 在仓库目录之外也可调用

#### Scenario: PATH hint when bin dir not on PATH
- **WHEN** `~/.local/bin` 不在用户 `PATH` 中
- **THEN** script 提示如何将其加入 PATH（或调用 uv 的 shell 更新）
- **AND** 不静默成功

#### Scenario: Install failure reports recovery hint
- **WHEN** `uv tool install` 未生成预期入口
- **THEN** script 告警并打印可手动复现的命令
- **AND** 以非零退出码退出

### Requirement: Decoupled state home
install script SHALL 将运行状态目录固定为 `FLEETENT_HOME`（默认 `~/.fleetent`），使全局命令与当前工作目录解耦。

#### Scenario: FLEETENT_HOME defaults to ~/.fleetent
- **WHEN** operator 运行默认 install
- **THEN** script 将 `FLEETENT_HOME` 设为 `~/.fleetent`
- **AND** 把该设置写入用户 shell rc（幂等：已存在则不重复写）

#### Scenario: Directory override
- **WHEN** operator 运行 install script with `--dir PATH`
- **THEN** script 使用 PATH 作为 `FLEETENT_HOME`，而非默认 `~/.fleetent`

### Requirement: Configuration templates
install script SHALL seed `.env` at `FLEETENT_HOME/.env` and the self-contained single-agent config at `FLEETENT_HOME/config/agent.yaml` from repository templates, preserving existing operator files. Global settings/mcp templates remain unseeded.

#### Scenario: Fresh install seeds config-dir agent yaml
- **WHEN** `FLEETENT_HOME/config/agent.yaml` or `.env` is absent
- **THEN** script creates `$FLEETENT_HOME/.env` from `.env.example`
- **AND** creates `$FLEETENT_HOME/config/agent.yaml` from `config/agent.yaml.example`

#### Scenario: Existing config-dir agent yaml or env is preserved
- **WHEN** `$FLEETENT_HOME/config/agent.yaml` or `.env` already exists
- **THEN** script leaves existing files unchanged

#### Scenario: Skip config skips seeding
- **WHEN** operator passes `--skip-config`
- **THEN** script does not seed `config/agent.yaml` or `.env`

### Requirement: Database initialization
install script SHALL 通过 Alembic 在 `FLEETENT_HOME/data` 下初始化 SQLite 数据库，使 schema lifecycle 统一归 Alembic 管理。

#### Scenario: Alembic upgrade runs on install
- **WHEN** operator 运行默认 install
- **THEN** script 针对 `$FLEETENT_HOME/data` 运行 `alembic upgrade head`
- **AND** 初始化数据库至最新 schema

#### Scenario: Skip database flag
- **WHEN** operator 运行 install script with `--skip-db`
- **THEN** script 不运行 Alembic migration

#### Scenario: Idempotent re-run
- **WHEN** operator 在已初始化的数据库上重复运行 install
- **THEN** `alembic upgrade head` 不重复应用已存在的 migration
- **AND** 不破坏已有数据

### Requirement: Optional dependency precheck
install script SHALL 检测沙箱所需的宿主 Docker，缺失时给出非阻断告警。

#### Scenario: Docker missing is non-blocking
- **WHEN** 宿主机未安装 Docker
- **THEN** script 告警「沙箱执行不可用」
- **AND** 继续完成安装，不以失败退出

#### Scenario: Docker present
- **WHEN** 宿主机已安装 Docker
- **THEN** script 不发出沙箱相关告警

### Requirement: Non-interactive flags
install script SHALL 支持非交互安装 flag，便于在 CI 或脚本化环境中运行。

#### Scenario: Skip flags are honored
- **WHEN** operator 传入 `--skip-db` 或 `--skip-config`
- **THEN** script 跳过对应步骤，其余步骤照常

#### Scenario: Unknown flag fails fast
- **WHEN** operator 传入未知 flag
- **THEN** script 打印错误与用法
- **AND** 以非零退出码退出

