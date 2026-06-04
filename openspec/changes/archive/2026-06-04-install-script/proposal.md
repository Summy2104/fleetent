## Why

fleetent 目前只有面向容器的部署路径（`Dockerfile` + `docker-compose.yml`）和面向已安装实例的升级脚本（`scripts/upgrade.py`），缺少**从零到可运行的单机 bootstrap**。开发者或试点 operator 想在一台干净的 Linux/macOS/WSL2 机器上快速跑起来，必须手动串联 uv 安装、依赖安装、配置模板拷贝、Alembic 初始化等步骤，易错且无幂等保证。本 change 提供一个 `scripts/install.sh` 一键安装器补齐这条路径：安装出**全局可用、与工作目录解耦**的 `fleetent` 命令（状态固定在 `~/.fleetent`），与 Docker 交付互补（Docker 面向 on-prem 生产，install.sh 面向开发者/单机快速体验）。

## What Changes

- 新增 `scripts/install.sh`：从干净环境 bootstrap，按固定顺序编排——环境净化 → 探测/安装 uv → 校验 Python 3.12 → `uv tool install` 安装全局命令 → 设定 `FLEETENT_HOME=~/.fleetent` 并拷贝 `.env.example` / `config/*.yaml.example` 到 `~/.fleetent/config` → `alembic upgrade head` 初始化 `~/.fleetent/data/users.db`。
- 用 **`uv tool install`** 安装 `fleetent`/`fleetent-admin`/`fleetent-tui` 三个 console-script 入口到 `~/.local/bin`，使命令**在任意目录可调用**；配合前置 change 的 `FLEETENT_HOME` 解析，config/data 固定在 `~/.fleetent`、与仓库目录解耦。
- 安装器**幂等可重入**：重复运行只补缺失项，不破坏已有 `~/.fleetent/.env`/`config`/数据库。
- 支持非交互 flags：`--skip-db`（跳过 Alembic 初始化）、`--skip-config`（跳过配置模板拷贝）、`--dir PATH`（覆盖 `FLEETENT_HOME`，默认 `~/.fleetent`）、`--help`。
- 沿用 hermes-agent install.sh 的工程实践：`set -e` fail-fast、开头清理继承的 `PYTHONPATH`/`PYTHONHOME` 防模块遮蔽、多地探测 uv（`PATH`→`~/.local/bin`→`~/.cargo/bin`）、彩色日志、失败时给出可手动复现的命令、`~/.local/bin` 不在 PATH 时提示如何加入。
- **不引入新运行时依赖**：sandbox 依赖宿主 Docker 这一既有事实仅做**预检告警**（缺 Docker 时提示沙箱不可用，不阻断安装）。

## Capabilities

### New Capabilities
- `install-bootstrap`: 单机一键安装契约——从干净环境 bootstrap 出**全局可用、与工作目录解耦**的 fleetent（uv tool 安装三入口到 PATH + `FLEETENT_HOME` 固定状态目录 + 配置模板 + 初始化数据库），幂等可重入，提供非交互安装 flags，并对缺失的可选依赖（Docker）给出非阻断告警。

### Modified Capabilities
<!-- 无：install bootstrap 是独立新能力，不改 deployment 既有的 upgrade/backup/restore 要求。 -->

## Impact

- **新增代码**：`scripts/install.sh`（bash）。
- **依赖前置**：`configurable-data-home`（提供 `FLEETENT_HOME` 路径解析）——本 change 必须在其合入 main 之后实施。
- **复用，不改**：`pyproject.toml` 的 `[project.scripts]` 三入口、`uv.lock`、`alembic.ini` + `migrations/`、`.env.example`、`config/*.yaml.example`。
- **测试**：`tests/integration/test_install_script.py`——以 `--help`/参数解析/幂等性/缺失依赖预检/`FLEETENT_HOME` 写入为主，临时 HOME/目录隔离（不触碰真实 `data/`/`~`）。进 PR 门禁。
- **不受影响**：`Dockerfile`/`docker-compose.yml`（容器路径不变）、`scripts/upgrade.py`（升级路径不变）、所有 Python 运行时模块。
- **平台范围**：Linux / macOS / WSL2（bash）。Windows 原生、Termux/Android 不在本 change 范围。
- **分支**：基于并合回 `main`。
