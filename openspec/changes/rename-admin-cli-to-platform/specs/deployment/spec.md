## MODIFIED Requirements

### Requirement: SQLite upgrade entry point

系统 SHALL 提供 `fleetent platform upgrade` 作为 SQLite-first on-prem upgrade entry point。
底层实现 MAY 复用本仓库的 upgrade helper/script，但用户文档和部署入口 SHALL 主推
`fleetent platform upgrade`。

#### Scenario: Upgrade command exists
- **WHEN** operator 查看 `fleetent platform --help`
- **THEN** 存在 `upgrade` 子命令

#### Scenario: Upgrade command reads effective database URL
- **WHEN** operator 运行 `fleetent platform upgrade`
- **THEN** command 使用 effective `database_url` 定位 SQLite DB 文件
- **AND** `--database-url` 优先于 `DATABASE_URL`
- **AND** `DATABASE_URL` 环境变量可以覆盖默认 settings

#### Scenario: Backup directory override
- **WHEN** operator 运行 `fleetent platform upgrade --backup-dir /tmp/backups`
- **THEN** command 使用该目录作为 backup root，而不是默认 `data/backups`

#### Scenario: Unsupported database URL fails fast
- **WHEN** database_url 不是本地 SQLite URL
- **THEN** command fail fast
- **AND** 不创建 backup
- **AND** 不运行 Alembic migration
