## Why

fleetent 的 config 与 data 路径目前是散落在 ~20 处模块里的硬编码相对常量（`Path("config/settings.yaml")`、`Path("data/fleetent.db")`、`Path("data/sessions")` 等），只能在仓库根目录运行。这阻断了"全局命令 + 与仓库目录解耦"的安装形态——用户在任意目录敲 `fleetent` 时，server 找不到 config/data。本 change 引入统一的运行时路径解析（`FLEETENT_HOME`），让所有路径常量从单一中心解析，使应用可运行在仓库外的固定家目录，是 `install-script` 全局安装的前置依赖。同时这也收口 CLAUDE.md 点名的"legacy 模块级路径常量"技术债。

## What Changes

- 新增 `src/fleetent/paths.py`：统一的运行时路径解析中心，导出 `config_dir()` / `data_dir()`（及派生的 settings/db/sessions 等路径），按固定优先级解析 base：
  1. 环境变量 `FLEETENT_HOME` 显式设置 → 用之（`$FLEETENT_HOME/config`、`$FLEETENT_HOME/data`）。
  2. 否则检测到仓库本地（CWD 存在 `pyproject.toml` 或 `./config`）→ 用 `./config`、`./data`（**开发态零改动**）。
  3. 否则回退默认家目录 `~/.fleetent`（`~/.fleetent/config`、`~/.fleetent/data`）。
- 将 ~20 处硬编码 `data/`、`config/` 路径常量改为从 `paths.py` 派生（config.py、server.py、agent_config.py、cron_scheduler.py、user_store.py、eval_logger.py、tools/builtin_tools.py、observability/*、integrations/sandbox/*、session/index.py、session/manager.py、model/router.py、platform/admin_cli/* 等）。
- 保持每个模块级路径常量**仍可被 `monkeypatch` 注入**（CLAUDE.md 硬性要求），中心解析器成为新的注入 seam（`monkeypatch.setenv("FLEETENT_HOME", ...)` 亦可整体重定向）。
- **只搬迁、不改名**：`fleetent.db` / `users.db` 等既有文件名维持现状映射到新 base，命名矛盾留作单独 cleanup（不在本 change）。

## Capabilities

### New Capabilities
- `runtime-paths`: 统一运行时路径解析契约——所有 config/data 路径从单一中心（`FLEETENT_HOME` → 仓库本地 → `~/.fleetent` 优先级）解析，使应用可运行在仓库外固定家目录；保持开发态（仓库内运行）零改动与路径常量的可注入性。

### Modified Capabilities
<!-- 无:本 change 只重定向路径解析,不改 deployment 的 upgrade/backup 行为契约、也不改各 store 的 SQL 契约。 -->

## Impact

- **新增代码**：`src/fleetent/paths.py`。
- **修改代码**：~20 处硬编码路径常量改为从 `paths.py` 派生（见上）。无 SQL 改动、无 schema 改动、无新依赖。
- **行为**：默认行为不变（仓库内运行仍用 `./config`+`./data`）；新增 `FLEETENT_HOME` 覆盖与无仓库时的 `~/.fleetent` 回退。
- **测试**：新增 `paths.py` 解析优先级单测；回归保护现有 monkeypatch 注入路径仍生效。
- **不受影响**：`db.py`（DB runtime 边界继续吃 `database_url`，本 change 只改 URL/path 的来源）、各 store 的 SQL、Alembic migrations、Docker 路径。
- **下游依赖**：`install-script` change 依赖本 change 完成后，方可用 `uv tool install` + `FLEETENT_HOME=~/.fleetent` 实现全局解耦安装。
- **分支**：基于并合回 `main`。
