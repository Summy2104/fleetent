## ADDED Requirements

### Requirement: Platform CLI namespace

系统 SHALL 提供 `fleetent platform` 作为 Platform/control-plane 的唯一本地 CLI
namespace。所有控制面 bootstrap、配置校验、基础设施供给、diagnostics 与危险维护命令
SHALL 位于该 namespace 下。系统 SHALL NOT 提供 `fleetent admin` 兼容 alias。

`admin` 一词仍可作为权限角色、built-in admin 用户和 HTTP `/admin/*` 路径语义存在；本
requirement 只约束 `fleetent` CLI namespace。

#### Scenario: Platform CLI dispatches

- **WHEN** operator 运行 `fleetent platform validate-config --format json`
- **THEN** CLI 调度到 Platform CLI，并以 `prog="fleetent platform"` 渲染 help/error

#### Scenario: Admin CLI namespace removed

- **WHEN** operator 运行 `fleetent admin validate-config`
- **THEN** CLI 不调度 Platform CLI
- **AND** 命令以未知 top-level command 失败

#### Scenario: Agent runtime does not import Platform CLI

- **WHEN** 调度到 `fleetent agent run`
- **THEN** Platform CLI 实现模块未被 import

### Requirement: Platform serve command

系统 SHALL 提供 `fleetent platform serve` 启动 Platform control-plane HTTP 服务。
该命令 SHALL 是 uvicorn 的薄封装，启动 `fleetent.server:app`，并支持至少
`--host`、`--port`、`--reload` 参数。服务生命周期仍由 `server.py`/ASGI app 拥有。

#### Scenario: Serve starts platform app

- **WHEN** operator 运行 `fleetent platform serve --host 127.0.0.1 --port 8770`
- **THEN** CLI 调用 uvicorn 启动 `fleetent.server:app`
- **AND** bind host 为 `127.0.0.1`
- **AND** bind port 为 `8770`

#### Scenario: Serve supports reload for development

- **WHEN** operator 运行 `fleetent platform serve --reload`
- **THEN** uvicorn 以 reload 模式启动 Platform app

### Requirement: Platform upgrade command

系统 SHALL 提供 `fleetent platform upgrade` 作为 SQLite-first on-prem upgrade 的用户入口。
该命令 SHALL 复用现有升级语义：定位 effective database URL、备份全部物理 SQLite 库、
兼容重命名 legacy `fleetent.db`、运行 Alembic migration、执行 default-agent backfill。
它 SHALL 支持 `--database-url`、`--backup-dir`、`--dry-run`、`--backup-only` 参数。

#### Scenario: Upgrade dry run

- **WHEN** operator 运行 `fleetent platform upgrade --dry-run`
- **THEN** 命令输出将执行的 backup / migration 操作
- **AND** 不创建 backup
- **AND** 不运行 Alembic migration

#### Scenario: Upgrade passes through backup options

- **WHEN** operator 运行 `fleetent platform upgrade --backup-dir /tmp/backups --backup-only`
- **THEN** upgrade 使用 `/tmp/backups` 作为 backup root
- **AND** 不运行 Alembic migration

### Requirement: Platform CLI keeps role terminology separate

CLI namespace SHALL use `platform` for the control-plane component. 权限角色 SHALL
continue to use existing role names (`admin`, `built_in_admin`, `viewer`) until a
separate authorization model change explicitly migrates them.

#### Scenario: Built-in admin seed remains a platform command

- **WHEN** operator 运行 `fleetent platform seed-builtin-admin`
- **THEN** 系统创建或复用 built-in admin 用户
- **AND** 用户 role 仍为 `built_in_admin`
