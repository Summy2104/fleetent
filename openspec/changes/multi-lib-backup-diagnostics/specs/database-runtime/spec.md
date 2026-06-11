## MODIFIED Requirements

### Requirement: Database runtime configuration
系统 SHALL 通过统一配置项 `database_url` 决定数据库 runtime 后端。当前版本 SHALL 默认使用
SQLite 管理库 `data/management.db`（持久层 #3 拆分后该库只剩跨主体管理表，文件名与概念名 `management.db` 对齐）。

#### Scenario: 默认 SQLite database_url
- **WHEN** 未显式配置 `database_url`
- **THEN** 系统使用指向 `data/management.db` 的 SQLite database_url

#### Scenario: 旧默认路径不隐式兼容
- **WHEN** 未显式配置 `database_url`
- **THEN** 系统不会自动读取、迁移、复制或 fallback 到旧默认路径 `data/users.db`

#### Scenario: 存量 users.db 需要 operator 手动处理
- **WHEN** operator 已有本地 `data/users.db`
- **THEN** 文档说明需要手动重命名为 `data/management.db` 或重新初始化
- **AND** runtime 不执行自动迁移

#### Scenario: 不支持的 database_url
- **WHEN** `database_url` 使用当前未实现的后端 scheme
- **THEN** database runtime 初始化失败，并明确说明该后端尚未支持

## ADDED Requirements

### Requirement: 管理库文件名迁移（fleetent.db → management.db）
持久层 #3 之前的管理库默认文件名为 `data/fleetent.db`。系统 SHALL 提供 upgrade-time 兼容迁移：当默认数据目录下存在旧文件 `fleetent.db` 而不存在 `management.db` 时，upgrade 流程 SHALL 将主文件连同其 `-wal` / `-shm` sidecar 重命名为 `management.db`，使存量部署平滑迁移而不丢数据、不破坏 WAL 状态。该迁移 SHALL 幂等：`management.db` 已存在时不再重命名。显式配置了 `database_url` / `DATABASE_URL` 指向自定义文件名的部署 SHALL NOT 被强制重命名。

#### Scenario: 旧 fleetent.db 自动迁移为 management.db
- **WHEN** 默认数据目录存在 `fleetent.db`（及其 WAL sidecar）而无 `management.db`，operator 运行 upgrade
- **THEN** `fleetent.db` / `fleetent.db-wal` / `fleetent.db-shm` 被重命名为 `management.db` / `management.db-wal` / `management.db-shm`
- **AND** 重命名在 backup 之后、Alembic migration 之前完成

#### Scenario: 已是 management.db 时迁移幂等
- **WHEN** 默认数据目录已存在 `management.db`，operator 运行 upgrade
- **THEN** 不执行任何重命名，已有数据原样保留

#### Scenario: 自定义 database_url 不被改名
- **WHEN** operator 显式设置 `DATABASE_URL` 指向非默认文件名的本地 SQLite
- **THEN** upgrade 不重命名该文件，按其配置路径操作
