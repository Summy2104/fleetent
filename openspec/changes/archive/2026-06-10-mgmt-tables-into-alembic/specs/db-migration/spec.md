## ADDED Requirements

### Requirement: 管理表收编完整性
`api_keys`、`audit_log`、`im_connectors`、`im_channel_allowlist` 这四张管理表 **MUST** 由 Alembic 迁移建立,其 store 模块 **MUST NOT** 再用 `_init_db` / `CREATE TABLE IF NOT EXISTS` 自建(落实既有「No raw schema creation in application code」对这四张的合规)。完成后管理库的 schema **MUST** 完全由 Alembic 拥有(连同 #2.5 已收编的 `users`)。

#### Scenario: 四张管理表由 alembic 建出
- **WHEN** 对空库执行 `alembic upgrade head`
- **THEN** schema 含 `api_keys`/`audit_log`/`im_connectors`/`im_channel_allowlist`,且这些 store 模块导入时不再调用建表 `_init_db`

#### Scenario: 已部署库迁移幂等
- **WHEN** 在已有这些表(由旧 `_init_db` 建)的库上执行迁移
- **THEN** 迁移幂等、不破坏既有数据(表已存在则 no-op)

#### Scenario: 启动不再自愈管理表
- **WHEN** 应用启动
- **THEN** 不对这四张表调用 `CREATE TABLE`;schema 须由先行的 `alembic upgrade head` 就绪
