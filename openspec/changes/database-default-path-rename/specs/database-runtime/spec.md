## MODIFIED Requirements

### Requirement: Database URL configuration
系统 SHALL 提供 `database_url` 配置，默认指向本机可持久化的 fleetent 主 SQLite 数据库
`data/fleetent.db`。

#### Scenario: Default database URL
- **WHEN** 未显式配置 database_url
- **THEN** 系统使用指向 `data/fleetent.db` 的 SQLite database_url

#### Scenario: Environment database URL override
- **WHEN** 通过环境变量配置 DATABASE_URL
- **THEN** 系统使用环境变量中的 database_url

#### Scenario: Unsupported database backend fails fast
- **WHEN** database_url 使用当前不支持的 backend
- **THEN** 系统 fail fast，并说明当前只支持 SQLite

### Requirement: No users.db compatibility fallback
系统 SHALL NOT 自动读取、迁移、复制或 fallback 到旧默认路径 `data/users.db`。

#### Scenario: Old default path is not used implicitly
- **WHEN** 未显式配置 database_url
- **THEN** 系统不会使用 `data/users.db`
- **AND** 系统不会因为 `data/users.db` 存在而自动改用旧路径

#### Scenario: Existing users.db requires manual operator action
- **WHEN** operator 已有本地 `data/users.db`
- **THEN** 文档说明需要手动重命名为 `data/fleetent.db` 或重新初始化
- **AND** runtime 不执行自动迁移
