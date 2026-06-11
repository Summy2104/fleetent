# user-blocklist Delta

## ADDED Requirements

### Requirement: 注册封禁表的 schema 权威为 Alembic
`blocked_registrations` 表 SHALL 仅由管理库 Alembic 迁移建立与演进（双权威契约：管理表 Alembic-only）。`governance/blocklist.py` SHALL NOT 在运行时自建表（不得含 `CREATE TABLE IF NOT EXISTS` / `_init_db` 路径），SHALL NOT re-export `user_store.DB_PATH`，SQL MUST 使用 named parameters（不得使用 `?` 占位符）。收编迁移 MUST 幂等承接存量部署中 store 既建的同构表（表已存在时不报错、不丢数据）。

#### Scenario: Alembic 建表
- **WHEN** 管理库 Alembic 迁移运行到最新版本（全新库）
- **THEN** `blocked_registrations` 表存在，含 email、reason、batch_id 与创建时间字段

#### Scenario: 存量自建表被幂等承接
- **WHEN** 存量部署的管理库中已有 store 自建的 `blocked_registrations` 表，运行收编迁移
- **THEN** 迁移成功且既有封禁行保留

#### Scenario: store 不再自建表
- **WHEN** 检查 `governance/blocklist.py` 源码
- **THEN** 模块内不存在 `CREATE TABLE` 语句与 `DB_PATH` re-export，所有 SQL 使用 named parameters

#### Scenario: 封禁行为不变
- **WHEN** platform block service 写入封禁、user_store 注册路径查询封禁
- **THEN** `ban_registration` / `is_registration_blocked` 行为与签名与收编前一致
