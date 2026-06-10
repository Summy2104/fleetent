## 1. 嵌入式迁移引擎（Y，基座）

- [x] 1.1 写失败测试：引擎核心行为——空库(v=0 跑全部步)、旧库(只跑增量步)、每步事务内 bump、失败回滚不前进、超前库(版本戳 > 代码当前)拒启动、空库与旧库同一路径（`tests/integration` 真实 SQLite 文件 + `PRAGMA user_version`）
- [x] 1.2 实现共享 Y 引擎（基座，`db.py` 邻近）：`MIGRATIONS=[(ver,sql)]` 接口 + `user_version` 读写 + migrate-on-open + 版本闸，跑绿 1.1
- [x] 1.3 写失败测试 + 实现：引擎为"各库供自己的清单与目标版本"的通用件（同一引擎驱动两个不同清单的库互不干扰）

## 2. KB 关系库的 MIGRATIONS 清单

- [x] 2.1 写失败测试：空 KB 关系库经 Y 迁移后，表/列/索引等价于现 `knowledge_base/operations.py:ensure_schema()` 的产出，且**含 `tenant_id`/`kb_id` 列**（建库后比对 schema）
- [x] 2.2 实现：把现 `ensure_schema()` 的 DDL 原样 lift 成 KB `MIGRATIONS`（v1..vN）放 `knowledge_base/core/`，跑绿 2.1（不改 schema，仅搬迁）

## 3. 租户作用域路由 + 可换后端抽象

- [x] 3.1 写失败测试：`scope(tenant)` 解析出 {KB 关系 db, KB 向量后端}；二者同源于一次解析；SQLite 后端把 `scope("default")` 映射到 `default` 主体目录文件；后端可替换（注入假后端验调用点不变）
- [x] 3.2 实现路由 + 可换后端抽象（基座/`db.py` 邻近）：`scope(tenant)`、SQLite 后端映射 `<tenant>/` 文件、单主体 `default` 直返（不做 fan-out），跑绿 3.1
- [x] 3.3 写失败测试 + 实现：经路由打开的受 Y 管理的库，**开库即触发 migrate-on-open**（路由 ↔ 引擎接合）

## 4. KB 连接走路由 + 清自连接旁路

- [x] 4.1 写失败测试：`KnowledgeStore` 的 `database` 来自路由；护栏断言 KB 模块**无** `create_database(...settings...)` 自连接路径
- [x] 4.2 实现：所有 `KnowledgeStore` 构造改由路由供连接；删 `knowledge_base/bindings.py`、`operations.py` 两条 `create_database(_settings().database_url)` 旁路，跑绿 4.1
- [x] 4.3 跑既有 KB 单测/集成（retrieval/ingest/operations）确认行为不变（连接来源改、语义不改）

## 5. 向量家族路由整改（§5.6）

- [x] 5.1 写失败测试：`VectorFamily` 枚举 + 单一 `family_of()`——已知前缀（`mem:`/`shared:`/`kb:`）归对应家族、未知前缀抛错（fail-fast）；既有 helper（`memory_namespace`/`knowledge_namespace`）返回值不变
- [x] 5.2 实现：引入 `VectorFamily` + `family_of()` 单一路由入口，替换散落的 ad-hoc `startswith`；KB 向量经同一 tenant-scope 路由到同主体向量后端，跑绿 5.1

## 6. 接合、护栏与收尾

- [x] 6.1 写失败测试 + 实现：boot 路径（`_start_infra`/agent_app）下 KB schema 经路由 + migrate-on-open 建立，不再由 KB `ensure_schema()` 建；其余 ensure_schema 库（traces/memory/reflection）行为不变
- [x] 6.2 写测试 + 实现：漂移护栏排除已迁入 Y 的 KB 表（KB 不在 ensure_schema↔alembic 校验范围）
- [x] 6.3 确认无 `import fleetent.platform.*`、无新增裸 `sqlite3.connect`、SQL 用 named parameters（跑依赖护栏 + `scripts/check_module_boundaries.py` 相关）
- [ ] 6.4 change 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败 + `openspec validate tenant-scoped-db-routing --strict`
