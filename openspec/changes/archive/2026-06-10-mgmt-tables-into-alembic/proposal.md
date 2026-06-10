## Why

`db-migration` 的「No raw schema creation in application code」已规定**管理表只经 alembic 建、不在应用代码 `CREATE TABLE`**。但仍有 4 张管理表用 store `_init_db` 自建、违反该要求:`api_keys`(api_key_store)、`audit_log`(audit_log.py)、`im_connectors`(connector_store)、`im_channel_allowlist`(channel_allowlist)。本变更把它们收编 alembic,**完成管理库 alembic 单权威**(`users` 已在 #2.5 establish-tenancy 收编)。

## What Changes

- 4 张表纳入 alembic 迁移(`CREATE TABLE IF NOT EXISTS` 形式:fresh 库由 alembic 建出、已部署库已有则 no-op);各 store **删除 `_init_db` 建表**。
- `im_channel_allowlist` 若源码内有重复 CREATE(§4-7 提及)→ 去重。
- **启动门**:这些管理表不再 `_init_db` 自愈,部署须先 `alembic upgrade head`(users 在 #2.5 已立此门,本期覆盖余下 4 张)。

> 不做:`approvals` 的 alembic 孤立定义(001/060)退场——它与"approvals 物理落哪"纠缠,**留 #3**(物理拆分时一并处理);其余非管理表(agent-side)走嵌入式迁移、本就不进 alembic(§5.2),不在本期。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `db-migration`: 新增一条"管理表收编完整性"requirement——`api_keys`/`audit_log`/`im_connectors`/`im_channel_allowlist` 由 alembic 建、store 不再 `_init_db`(把既有"No raw schema creation"要求落到这 4 张的具体合规)。

## Impact

- **迁移**:新 alembic 迁移建/确保 4 张管理表;`downgrade` 相应。
- **代码**:`platform/user_management/api_key_store.py`、顶层 `audit_log.py`、`platform/im_gateway_management/connector_store.py`、`platform/im_gateway_management/channel_allowlist.py` —— 各删 `_init_db` 建表(改依赖 alembic 已建)。
- **启动门**:部署须先 `upgrade head`。
- **零业务行为变更**:表结构不变,仅建表权威从 `_init_db` 迁到 alembic;既有数据不动。
