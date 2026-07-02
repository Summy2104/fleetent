## Why

当前用户入口与架构语言不一致：控制面在架构、UI、Makefile target 中叫
**Platform**，但 CLI namespace 叫 `fleetent admin`。`admin` 描述的是权限角色，
不是系统组件；而现有 CLI 实际承担的是 Platform/control-plane 运维：配置初始化、
配置校验、node registry、diagnostics、maintenance、KB 维护等。

同时 Platform 启动和升级仍散落在 `uvicorn fleetent.server:app`、`alembic upgrade
head`、`scripts/upgrade.py`、Makefile 与 shell installer 中。继续增加 `fleetent
platform ...` 与 `fleetent admin ...` 并存会制造两套心智模型。应直接统一为
`fleetent platform ...`，不保留 `fleetent admin` 兼容 alias。

## What Changes

- **CLI namespace breaking rename**：删除 `fleetent admin ...` 调度入口，新增
  `fleetent platform ...` 作为 Platform/control-plane 唯一 CLI namespace。
- **模块命名收口**：将 `platform/admin_cli` 迁移为 `platform/platform_cli`（或等价
  `platform/cli`），测试与文档不再称其为 admin CLI。
- **Platform serve 收口**：新增 `fleetent platform serve`，薄封装 uvicorn 启动
  `fleetent.server:app`；Makefile、Docker entrypoint、安装脚本输出、开发文档改用该入口。
- **Platform upgrade 收口**：新增 `fleetent platform upgrade`，复用现有
  `scripts/upgrade.py` 的 backup / legacy rename / Alembic / backfill 语义；
  `scripts/upgrade.py` 可保留为实现载体或 thin wrapper，但用户文档主推新入口。
- **配置/维护命令迁移**：现有 `seed-builtin-admin`、`init-config`、`validate-config`、
  `node ...`、`diagnostics ...`、`maintenance ...`、`kb ...` 均迁到
  `fleetent platform ...`。
- **保留 admin 作为权限角色**：`admin`、`built_in_admin`、`viewer` 等角色名不变；
  HTTP `/admin/*` 与 `/admin/ui` 暂不迁移，避免把 API/前端路径重命名混入本切片。

## Capabilities

### New Capabilities

- `platform-cli`：Platform/control-plane 的唯一本地 CLI namespace。

### Modified Capabilities

- `configuration`：配置初始化入口从 `fleetent admin init-config` 改为
  `fleetent platform init-config`。
- `deployment`：升级入口从 `scripts/upgrade.py`/直接 Alembic 主推形式改为
  `fleetent platform upgrade`；Platform 服务启动入口改为 `fleetent platform serve`。
- `install-platform-script`：安装脚本输出与内部 seed 命令改用 `fleetent platform ...`。
- `module-boundaries`：原 `admin_cli` 直写边界改名为 Platform CLI 边界，语义不变：
  只允许 bootstrap、基础设施供给、危险宿主级维护，不做业务 CRUD。

## Impact

**owning package**：`platform/platform_cli`（由 `platform/admin_cli` 迁移而来）、
`src/fleetent/__main__.py`、Platform 启动/升级 thin wrapper。

**public API surface**：
- 删除：`fleetent admin ...`
- 新增：`fleetent platform ...`
- 新增：`fleetent platform serve [--host HOST] [--port PORT] [--reload]`
- 新增：`fleetent platform upgrade [--database-url URL] [--backup-dir PATH] [--dry-run] [--backup-only]`

**owned tables**：无。

**config namespace**：无新增配置 namespace；`serve` 读取现有 `FLEETENT_HOME`、
`DATABASE_URL`、`platform.yaml`、`.env` 约定。

**cross-module dependencies**：Platform CLI 可 import `fleetent.platform.*`、`server`
启动入口和 upgrade helper；`fleetent agent run`、`fleetent node start`、
`fleetent kb worker` 仍必须懒加载，不因新增 platform CLI 破坏 agent/platform 解耦。

**migration / shim plan**：不保留 `fleetent admin` alias；这是显式 breaking change。
HTTP `/admin/*` 不迁移；代码内部角色名与权限语义不迁移。
