## MODIFIED Requirements

### Requirement: Database runtime configuration

系统默认 SHALL 使用 Platform home 根目录下的 SQLite 管理库 `management.db`（持久层 tenant-first 拆分后该库只剩跨主体管理表，文件名与概念名 `management.db` 对齐）。

#### Scenario: DATABASE_URL 未设置时使用根目录 management.db
- **WHEN** 未设置 `DATABASE_URL`
- **THEN** 系统使用指向 `<FLEETENT_HOME>/management.db` 的 SQLite database_url

#### Scenario: DATABASE_URL 仍优先
- **WHEN** 设置了 `DATABASE_URL`
- **THEN** 系统使用该显式 URL
- **AND** 不强制改写为默认路径
