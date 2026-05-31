## Why

fleetent 当前是 SQLite-first，但数据库访问细节已经从 store 层泄漏出来：
`DB_PATH`、直接 `sqlite3.connect()`、`?` 占位符、SQLite 专属 `PRAGMA`、以及 store 内部
`CREATE TABLE IF NOT EXISTS` 建表/补列逻辑都在扩散。

如果继续沿用这个模式，后续即使只把 PostgreSQL 作为可选生产后端，也会变成大规模重构。
本 change 先建立很薄的数据库 runtime 边界，保持当前只支持 SQLite，不引入 ORM。

## What Changes

- 新增 `database-runtime` 能力：定义 store 模块访问数据库的统一 runtime 边界。
- 当前只实现 SQLite adapter；PostgreSQL adapter 不在本 change 范围内。
- 新增 `database_url` 配置，默认指向本机 `data/users.db`。
- 新增或迁移后的 store SQL 必须使用 named parameters，例如 `:user_id`。
- 禁止新数据库代码继续直接依赖 `sqlite3.connect`、`DB_PATH` re-export、SQLite-only
  `PRAGMA` 检查、或 store-local `_init_db()` 建表/补列模式。
- 调整 `db-migration` 规范：schema lifecycle 归 Alembic 管理；当前 backend 是 SQLite，
  但新规范不再把项目描述为 SQLite-only。
- 迁移一个低风险 store 作为参考实现，后续 store 分批迁移，不在本 change 一次性完成。

## Capabilities

### New Capabilities

- `database-runtime`：统一数据库配置、连接、事务、row/result 包装、adapter 边界。

### Modified Capabilities

- `db-migration`：明确 Alembic 管理 database schema lifecycle；当前 migration 仍面向 SQLite，
  但新工作不得继续假设项目永远只有 SQLite。

## Impact

- **代码**：
  - 新增 `src/fleetent/db.py` 或等价 runtime 模块。
  - 在 settings/config 中新增 `database_url`，默认使用 SQLite。
  - 迁移一个低风险 store，优先 `schedule_store`，作为新 runtime 的参考模式。
  - 增加 runtime 配置、named parameters、事务、迁移后 store 行为的测试。
- **文档 / 流程**：
  - Agent 指令已明确 SQLite-first、禁止 ORM、named parameters、Alembic 管 schema。
  - 架构和 deployment 文档已记录 SQLite-first 以及 PostgreSQL 迁移空间。
- **依赖**：
  - 不引入 ORM。
  - 不引入 PostgreSQL driver。
- **兼容性**：
  - 现有 legacy store 可以保留当前 SQLite 实现，等待后续分批迁移。
  - 新增或被本 change 触碰的数据库代码必须走 runtime 边界。
