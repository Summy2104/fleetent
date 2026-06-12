# im-user-mapping Delta

## ADDED Requirements

### Requirement: im_users schema 权威为 Alembic
`im_users` 表 SHALL 仅由管理库 Alembic 迁移建立与演进（双权威契约：管理表 Alembic-only）。`platform/im_gateway_management/identity.py` SHALL NOT 在运行时自建表（不得含 `CREATE TABLE` / `_init_db` 路径），SHALL NOT re-export `user_store.DB_PATH`，SQL MUST 使用 named parameters（不得使用 `?` 占位符）。`im_user_store` 兼容 shim SHALL NOT re-export `_init_db`。

#### Scenario: store 不再自建表
- **WHEN** 检查 `platform/im_gateway_management/identity.py` 源码
- **THEN** 模块内不存在 `CREATE TABLE` 语句、`_init_db` 函数与 `DB_PATH` re-export，所有 SQL 使用 named parameters

#### Scenario: 热路径解析不跑建表检查
- **WHEN** managed 模式下注入的身份 resolver 处理一条 IM 消息（调用 `get_or_create`）
- **THEN** 解析路径不执行任何 `CREATE TABLE` / schema 检查语句

#### Scenario: 行为不变
- **WHEN** 经 Alembic 建好 schema 的管理库上调用 `get_or_create` / `approve_user` / `block_user` / `list_*`
- **THEN** 各函数行为与签名与清理前一致

#### Scenario: shim 导出面缩减
- **WHEN** 检查 `fleetent.im_user_store` shim
- **THEN** 不再 re-export `_init_db`；其余既有 re-export 保持
