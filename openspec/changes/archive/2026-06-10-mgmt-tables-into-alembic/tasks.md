> TDD;迁移须**幂等 + 可逆往返 + 在已有这些表的库上安全**(不丢数据)。列定义须与各 store 原 `_init_db` 逐字对齐(防 fresh/旧库漂移)。

## 1. 迁移前比对

- [x] 1.1 抄出 4 个 store 现有 `_init_db` 的建表 DDL(`api_key_store`/`audit_log`/`connector_store`/`channel_allowlist`),作为 alembic 迁移建表的依据;核查 `im_channel_allowlist` 是否有重复 CREATE。

## 2. alembic 收编迁移

- [x] 2.1 写失败测试(`tests/integration/`):空库 `alembic upgrade head` 后 schema 含 `api_keys`/`audit_log`/`im_connectors`/`im_channel_allowlist`(列与原 `_init_db` 一致)。先见红。
- [x] 2.2 新增 alembic 迁移:`CREATE TABLE IF NOT EXISTS` 这 4 张(列对齐 1.1);`downgrade` 相应。见绿。
- [x] 2.3 幂等/可逆:在"已有这些表"的库上跑迁移 no-op、不丢数据;空库 `upgrade→downgrade→upgrade` 往返通过。

## 3. 各 store 去 _init_db

- [x] 3.1 写失败/守卫测试:导入这 4 个 store 模块时**不**建表;模块内无 `CREATE TABLE`(`api_keys`/`audit_log`/`im_connectors`/`im_channel_allowlist`)。先见红。
- [x] 3.2 删除 4 个 store 的 `_init_db` 建表逻辑(保留 CRUD;经 db.py runtime、named params);`im_channel_allowlist` 若有重复 CREATE 一并去重。见绿。
- [x] 3.3 写/跑 server + 各 admin API 既有测试:确认去 `_init_db` 后(schema 由 alembic 就绪)功能无回归。

## 4. 收尾验证

- [x] 4.1 `make test-pr` 全绿。
- [x] 4.2 `uv run pytest tests/integration -q` 对照 main 无新增失败(含"已有数据库"上迁移幂等)。
- [x] 4.3 `openspec validate mgmt-tables-into-alembic` 通过。
- [x] 4.4 复核:未碰 approvals 的 alembic 定义(留 #3);未碰 agent-side 表;部署文档标注"部署须先 alembic upgrade head"。
