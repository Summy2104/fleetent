# database-runtime Delta

## ADDED Requirements

### Requirement: 外键强制启用（foreign_keys=ON）
经 `db.py` 取得的全部 SQLite 连接 MUST 在连接初始化时执行 `PRAGMA foreign_keys=ON`（与 WAL、busy_timeout 同处设置）。自此声明了外键的库（管理库 Alembic schema、KB 关系库嵌入式 DDL 的 `ON DELETE CASCADE`）其约束与级联为**真实生效语义**，不再是装饰性声明。写路径违反 FK MUST 失败（fail loud），不得静默产生孤儿引用。

#### Scenario: 连接启用 FK 强制
- **WHEN** 经 `db.py` 打开任一 SQLite 连接并查询 `PRAGMA foreign_keys`
- **THEN** 返回 1（启用）

#### Scenario: 违反 FK 的写入被拒
- **WHEN** 向管理库插入 `agents` 行且其 `tenant_id` 不存在于 `tenants`
- **THEN** 写入失败并报 FK 约束错误，不产生孤儿行

#### Scenario: KB 级联真实生效
- **WHEN** 删除一行 `knowledge_documents`
- **THEN** 其下属 `knowledge_chunks` 行随 `ON DELETE CASCADE` 一并删除，不留孤儿 chunk
