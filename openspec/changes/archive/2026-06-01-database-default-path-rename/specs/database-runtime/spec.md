## MODIFIED Requirements

### Requirement: Database runtime configuration
系统 SHALL 通过统一配置项 `database_url` 决定数据库 runtime 后端。当前版本 SHALL 默认使用
SQLite 数据库 `data/fleetent.db`。

#### Scenario: 默认 SQLite database_url
- **WHEN** 未显式配置 `database_url`
- **THEN** 系统使用指向 `data/fleetent.db` 的 SQLite database_url

#### Scenario: 旧默认路径不隐式兼容
- **WHEN** 未显式配置 `database_url`
- **THEN** 系统不会自动读取、迁移、复制或 fallback 到旧默认路径 `data/users.db`

#### Scenario: 存量 users.db 需要 operator 手动处理
- **WHEN** operator 已有本地 `data/users.db`
- **THEN** 文档说明需要手动重命名为 `data/fleetent.db` 或重新初始化
- **AND** runtime 不执行自动迁移

#### Scenario: 不支持的 database_url
- **WHEN** `database_url` 使用当前未实现的后端 scheme
- **THEN** database runtime 初始化失败，并明确说明该后端尚未支持
