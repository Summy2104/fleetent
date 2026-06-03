# deployment Specification

## Purpose
定义 on-prem deployment 的本地升级、备份和恢复基础能力，确保 SQLite-first 部署在 schema migration 前有可操作的备份和失败恢复路径。
## Requirements
### Requirement: SQLite upgrade entry point
系统 SHALL 提供 `scripts/upgrade.py` 作为 SQLite-first on-prem upgrade entry point。

#### Scenario: Upgrade script exists
- **WHEN** operator 查看仓库 scripts
- **THEN** 存在 `scripts/upgrade.py`

#### Scenario: Upgrade script reads effective database URL
- **WHEN** operator 运行 upgrade script
- **THEN** script 使用 effective `database_url` 定位 SQLite DB 文件
- **AND** `--database-url` 优先于 `DATABASE_URL`
- **AND** `DATABASE_URL` 环境变量可以覆盖默认 settings

#### Scenario: Backup directory override
- **WHEN** operator 运行 upgrade script with `--backup-dir`
- **THEN** script 使用该目录作为 backup root，而不是默认 `data/backups`

#### Scenario: Unsupported database URL fails fast
- **WHEN** database_url 不是本地 SQLite URL
- **THEN** script fail fast
- **AND** 不创建 backup
- **AND** 不运行 Alembic migration

### Requirement: Pre-migration SQLite backup
upgrade script SHALL 在运行 Alembic migration 前创建 SQLite DB 文件备份。

#### Scenario: Backup is created before migration
- **WHEN** operator 运行默认 upgrade
- **THEN** script 在 `data/backups/YYYYMMDD-HHMMSS/fleetent.db` 创建 DB 备份
- **AND** backup 成功后才运行 `alembic upgrade head`

#### Scenario: Backup directory is created
- **WHEN** backup directory 不存在
- **THEN** script 创建该目录

#### Scenario: Missing database file fails fast
- **WHEN** database_url 指向的 SQLite DB 文件不存在
- **THEN** script fail fast
- **AND** 错误信息说明 database file 不存在
- **AND** 不运行 Alembic migration

### Requirement: Upgrade dry run
upgrade script SHALL 支持 dry-run，用于显示将执行的 backup 和 migration 操作而不修改文件系统。

#### Scenario: Dry run does not write or migrate
- **WHEN** operator 运行 `scripts/upgrade.py --dry-run`
- **THEN** script 输出将备份的 DB 路径和 migration 命令
- **AND** 不要求 SQLite DB 文件已经存在
- **AND** 不创建 backup 文件
- **AND** 不运行 Alembic migration

### Requirement: Backup-only mode
upgrade script SHALL 支持 backup-only，用于只创建 SQLite DB 备份而不运行 migration。

#### Scenario: Backup-only skips migration
- **WHEN** operator 运行 `scripts/upgrade.py --backup-only`
- **THEN** script 创建 backup
- **AND** 不运行 Alembic migration

### Requirement: Migration failure handling
upgrade script SHALL 在 migration 失败时保留 backup 并返回非 0 exit code。

#### Scenario: Alembic failure keeps backup
- **WHEN** backup 成功但 `alembic upgrade head` 失败
- **THEN** script 返回非 0 exit code
- **AND** 已创建 backup 保留在 backup directory
- **AND** script 输出手动恢复提示

#### Scenario: Backup failure prevents migration
- **WHEN** backup 创建失败
- **THEN** script 返回非 0 exit code
- **AND** 不运行 Alembic migration

### Requirement: Manual restore documentation
部署文档 SHALL 说明 upgrade 失败后的手动恢复步骤。

#### Scenario: Restore steps are documented
- **WHEN** operator 查看 deployment 文档
- **THEN** 文档说明恢复步骤：停止服务、用备份 DB 替换当前 DB、重启服务
- **AND** 文档说明 migration 失败不会自动 rollback

### Requirement: Upgrade excludes install package scope
deployment upgrade SHALL NOT introduce full install package, license, PostgreSQL backup, retention policy, UI,
API, scheduler, or worker behavior.

#### Scenario: Upgrade remains local script
- **WHEN** 本 change 完成
- **THEN** upgrade 能力通过 local script 提供
- **AND** 不新增 Admin API、HTTP endpoint、dashboard、scheduler 或 worker

### Requirement: Pilot connector operation guidance
部署文档 SHALL 说明 Pilot 环境中如何配置、检查、手动同步和排查 knowledge-base connectors。

#### Scenario: Connector CLI commands are documented
- **WHEN** operator 阅读部署或运维文档
- **THEN** 文档列出 `fleetent-admin kb connectors list/check/status/sync` 的用途

#### Scenario: Credential boundary is documented
- **WHEN** operator 阅读部署或运维文档
- **THEN** 文档说明真实 credential 不应写入 `settings.yaml`
- **AND** 文档说明 `credential_ref` 指向的文件或环境变量需要由部署方保护权限

#### Scenario: Connector troubleshooting is documented
- **WHEN** connector check 或 sync 返回 credential_missing、auth_failed、scope_unreachable 或 sync_failed
- **THEN** 文档提供对应的排查方向

### Requirement: Diagnostics and retention deployment guidance
部署文档 SHALL 说明 Pilot 环境中的 diagnostics export 和手动 retention 操作边界。

#### Scenario: Diagnostics export is documented
- **WHEN** operator 阅读 deployment 文档
- **THEN** 文档说明如何运行 `fleetent-admin diagnostics export`
- **AND** 文档说明诊断包包含和不包含的内容

#### Scenario: Retention default is documented
- **WHEN** operator 阅读 deployment 文档
- **THEN** 文档说明默认不设置保留时长
- **AND** 默认不自动清理

#### Scenario: Manual retention is documented
- **WHEN** operator 阅读 deployment 文档
- **THEN** 文档说明如何运行 `fleetent-admin diagnostics retention dry-run`
- **AND** 文档说明只有显式开启 `diagnostics.retention.enabled=true` 后 apply 才会删除诊断数据

#### Scenario: Backup deletion is out of scope
- **WHEN** operator 阅读 deployment 文档
- **THEN** 文档说明 diagnostics retention 不删除 SQLite backups
- **AND** 数据库备份保留策略由部署方单独管理

### Requirement: Pilot install checklist
部署文档 SHALL 提供 Pilot MVP 安装清单，按 operator 执行顺序覆盖安装、升级、备份、启动、健康检查、排障、回滚和验收。

#### Scenario: Checklist document exists
- **WHEN** operator 查看 deployment 文档
- **THEN** 文档引用 `docs/deployment/pilot-install-checklist.md`
- **AND** checklist 使用中文说明 Pilot 安装与验收步骤

#### Scenario: Checklist covers install and upgrade
- **WHEN** operator 阅读 checklist
- **THEN** checklist 包含前置条件、配置、`scripts/upgrade.py --dry-run`、SQLite backup、`alembic upgrade head`、服务启动和 `/health` 检查

#### Scenario: Checklist covers Pilot operations
- **WHEN** operator 阅读 checklist
- **THEN** checklist 包含 KB connector check / sync / status、observability traces / usage / performance 查询、diagnostics export / retention dry-run

#### Scenario: Checklist covers rollback and reporting
- **WHEN** operator 阅读 checklist
- **THEN** checklist 包含从 SQLite backup 手动恢复、停止服务、重启服务、回滚后 health check 和问题上报包

#### Scenario: Checklist excludes secrets
- **WHEN** operator 阅读 checklist 或准备问题上报包
- **THEN** checklist 明确禁止把真实 secret、token、credential payload 写入 settings、日志、trace、diagnostics package、issue 或测试 fixture

### Requirement: Fleetent admin command compatibility
部署 SHALL 继续提供 `fleetent-admin` 作为管理员和 operator 的本机 CLI 入口。

#### Scenario: Fleetent admin command remains available
- **WHEN** operator 按部署文档运行 `uv run fleetent-admin`
- **THEN** CLI 使用新的 `platform.admin_cli` 实现
- **AND** 对 operator 暴露的命令名、参数和输出保持兼容

### Requirement: Pilot acceptance guide
部署文档 SHALL 提供测试环境 Pilot 人工验收指南，用于判断当前系统是否可以进入小范围真实用户试用。

#### Scenario: Acceptance guide exists
- **WHEN** operator 查找 Pilot 验收步骤
- **THEN** `docs/deployment/pilot-acceptance-guide.md` 存在
- **AND** 文档说明它用于安装完成后的人工验收

#### Scenario: Acceptance guide covers environment and configuration
- **WHEN** operator 按指南准备测试环境
- **THEN** 指南覆盖配置文件、secret、MCP server file、credential_ref、数据库路径和外部依赖检查

#### Scenario: Acceptance guide covers operational safety
- **WHEN** operator 按指南执行部署验收
- **THEN** 指南覆盖 SQLite backup、upgrade、backup-only、dry-run 和 restore drill

#### Scenario: Acceptance guide covers capability smoke checks
- **WHEN** operator 按指南执行功能验收
- **THEN** 指南覆盖 observability、diagnostics、memory、long-term context、reflection、knowledge base、vector reindex 和 embedding / rerank smoke

#### Scenario: Acceptance guide distinguishes skipped external smoke
- **WHEN** 真实 LLM、embedding、Google Drive 或 Confluence 凭据未配置
- **THEN** 指南要求把对应 smoke 记录为 skipped
- **AND** 不把显式未配置的外部依赖默认判定为验收失败

#### Scenario: Acceptance guide defines Go / No-Go
- **WHEN** 验收完成
- **THEN** 指南提供 Go、Conditional Go 和 No-Go 判定标准
- **AND** 指南提供问题记录和验收报告模板

### Requirement: Docker Compose Pilot deployment entrypoint
部署 SHALL 提供 Docker Compose 作为 Pilot 默认部署入口，同时保留源码 `uv run uvicorn` 作为开发模式。

#### Scenario: Compose service is the documented Pilot default
- **WHEN** operator 阅读 Pilot 部署文档或 runbook
- **THEN** 文档优先使用 `docker compose` 流程启动 fleetent
- **AND** 源码 `uv run uvicorn fleetent.server:app` 只标注为开发模式

#### Scenario: Compose exposes the standard Pilot port
- **WHEN** operator 使用 docker compose 启动 fleetent
- **THEN** 服务通过 `http://127.0.0.1:8765/health` 做 health check
- **AND** 文档中的 Pilot 默认端口为 `8765`

#### Scenario: Compose mounts deployment state directories
- **WHEN** operator 查看 `docker-compose.yml`
- **THEN** compose 挂载 `./data:/app/data`
- **AND** 挂载 `./config:/app/config`
- **AND** 挂载 `./secrets:/app/secrets:ro`

#### Scenario: Compose uses local env file
- **WHEN** operator 查看 `docker-compose.yml`
- **THEN** compose 使用 `.env`
- **AND** 不引用 `.env.production`

### Requirement: Container image includes deployment tooling
Docker image SHALL include enough project files to run the service, admin CLI and SQLite upgrade script inside the container.

#### Scenario: Container includes runtime and migration assets
- **WHEN** Docker image is built
- **THEN** image contains `src/`, `migrations/`, `scripts/`, `alembic.ini`, `pyproject.toml` and `uv.lock`

#### Scenario: Container can run operator commands
- **WHEN** operator enters the fleetent container or uses `docker compose run --rm fleetent`
- **THEN** `uv run fleetent --help` works
- **AND** `uv run fleetent-admin --help` works
- **AND** `uv run python scripts/upgrade.py --dry-run` works

### Requirement: Explicit migration is recommended for Pilot
Pilot deployment docs SHALL recommend explicit migration before service startup, while allowing optional auto-upgrade only by explicit opt-in.

#### Scenario: Pilot migration is explicit
- **WHEN** operator follows Pilot deployment runbook
- **THEN** operator runs `docker compose run --rm fleetent uv run python scripts/upgrade.py`
- **AND** only after successful upgrade runs `docker compose up -d`

#### Scenario: Auto-upgrade is disabled by default
- **WHEN** `FLEETENT_AUTO_UPGRADE` is unset or false
- **THEN** container startup does not run `scripts/upgrade.py`

#### Scenario: Auto-upgrade is opt-in
- **WHEN** `FLEETENT_AUTO_UPGRADE=true`
- **THEN** container entrypoint runs `uv run python scripts/upgrade.py` before starting uvicorn
- **AND** startup fails if upgrade fails

### Requirement: Docker deployment docs cover secrets and init flow
Deployment docs SHALL explain the Docker Compose first Pilot flow, local env file, flat secrets directory and config initialization.

#### Scenario: Init flow is documented
- **WHEN** operator reads deployment docs
- **THEN** docs instruct operator to run `fleetent-admin init-config`
- **AND** docs explain which files and directories are created

#### Scenario: Flat secrets directory is documented
- **WHEN** operator reads deployment docs
- **THEN** docs state `secrets/` is a flat deployment-level directory
- **AND** docs give examples such as `google-drive-token.json` and `confluence-api-token`
- **AND** docs state file names do not express connector scope

#### Scenario: Secret files are excluded from reports
- **WHEN** operator prepares diagnostics or issue evidence
- **THEN** docs prohibit including files from `secrets/`
- **AND** docs require using credential references rather than credential payloads
