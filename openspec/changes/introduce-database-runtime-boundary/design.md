## Context

fleetent 当前的数据库代码以 SQLite 为中心，多个 store 直接 import `sqlite3`、暴露或复用
`DB_PATH`、使用 `?` 参数占位符，并在 store 内部通过 `_init_db()` 建表或补列。这个模式对早期
MVP 简单有效，但会让后续 PostgreSQL 可选后端、统一测试隔离、schema migration 收敛都变得困难。

本设计不是要立刻支持 PostgreSQL，也不是要引入 ORM，而是先建立一条轻量边界：业务 store 继续手写
SQL，但通过统一 database runtime 获取连接、事务和结果对象。SQLite 是当前唯一实现，接口形状为后续
adapter 留出空间。

## Goals / Non-Goals

**Goals:**

- 定义 `fleetent.db` runtime 边界，当前只实现 SQLite adapter。
- 新增 `database_url` 配置，默认指向 `sqlite:///data/users.db`。
- 规定新/迁移后的 store 使用 named parameters，例如 `:task_id`、`:user_id`。
- 让 store 不再直接依赖 `sqlite3.connect()`、`DB_PATH` re-export 或 SQLite-only schema 检查。
- 用一个低风险 store（优先 `schedule_store`）作为参考迁移，验证接口足够支撑真实调用。
- 保持现有 legacy store 可逐步迁移，不在本 change 一次性改完。

**Non-Goals:**

- 不实现 PostgreSQL adapter。
- 不引入 SQLAlchemy ORM、SQLModel、Peewee 或其他 ORM。
- 不引入 query builder。
- 不把所有 store 一次性迁移到新 runtime。
- 不把同步 store 调用链改成 async。

## Decisions

### 1. 使用薄 DB adapter，而不是 ORM

`fleetent.db` 定义 `Database` / `DbConnection` / `DbResult` 这类最小接口，当前实现
`SQLiteDatabase`。store 层继续手写 SQL，保持可审计性和部署可控性。

备选方案：

- 完整 ORM：迁移成本高，隐式行为多，不符合当前“最少依赖、直接可审计”的项目哲学。
- 只包一层 `connect()`：太薄，无法阻止 SQLite 参数风格、裸 cursor、row 格式继续泄漏。

### 2. 第一版保持同步接口

当前 store 都是同步函数，SQLite 本身也无法通过 async 包装解决单写限制。第一版 runtime 保持同步，
降低迁移成本。未来如果 PostgreSQL adapter 需要 async driver，应另开 change 评估调用链影响。

### 3. SQL 参数统一为 named parameters

新/迁移后的 store 必须使用 `:name` 风格参数，并传入 `Mapping[str, object]`：

```python
db.execute(
    "SELECT * FROM scheduled_tasks WHERE id = :task_id",
    {"task_id": task_id},
)
```

SQLite 原生支持 named parameters。后续 PostgreSQL adapter 可在 adapter 层转换参数风格，避免 store
层散落 `?` 或 `%s`。

### 4. `database_url` 是配置入口，SQLite 是唯一当前 backend

新增 `Settings.database_url`，默认值为 `sqlite:///data/users.db`。`fleetent.db` 根据 URL 创建
adapter。当前如果传入非 SQLite URL，应明确报错，避免用户误以为 PostgreSQL 已支持。

### 5. Alembic 管 schema，runtime 不负责建表

runtime 只负责连接、事务和结果，不负责自动建表。迁移后的 store 不再复制 `_init_db()` 建表/补列模式。
现有 legacy store 可保留旧逻辑，等待后续迁移。

### 6. 参考迁移选择 `schedule_store`

`schedule_store` 数据模型小、外部调用面清晰，适合验证：

- named parameters
- transaction 上下文
- row 转 dict
- 测试隔离从 monkeypatch `DB_PATH` 迁移到 database_url/runtime fixture

暂不迁移 `user_store`，因为它是认证、API key、IM 映射等多个模块的隐式地基，第一版直接迁移风险较高。

## Risks / Trade-offs

- **风险：adapter 太薄，后续仍要重构。** → 通过参考迁移真实 store 来验证接口，不只写空 wrapper。
- **风险：adapter 太厚，变成自制 ORM。** → 只暴露连接、事务、execute/result，不做模型映射或 query builder。
- **风险：legacy store 与新 runtime 并存造成风格混杂。** → AGENTS/CLAUDE 规则明确新代码不得扩散旧模式，后续分批迁移。
- **风险：`database_url` 让用户误以为 PostgreSQL 可用。** → 非 SQLite URL 当前必须 fail fast，并在错误信息中说明 PostgreSQL 未实现。
- **风险：测试仍依赖 `DB_PATH` monkeypatch。** → 本 change 的新增测试使用 runtime 配置隔离；legacy 测试保持不动。

## Migration Plan

1. 新增 runtime 和配置，默认行为仍指向 `data/users.db`。
2. 添加 runtime 单元测试，覆盖 SQLite URL、非 SQLite fail fast、named parameters、事务提交/回滚、row/result 行为。
3. 迁移 `schedule_store` 到 runtime，保留外部函数签名不变。
4. 更新 `schedule_store` 测试使用统一 database_url/runtime 隔离。
5. 运行项目 TDD 验证命令，确保既有行为不变。

回滚策略：runtime change 不修改数据库 schema；如果出现问题，可回滚 `schedule_store` 到 legacy `DB_PATH`
实现，数据库文件保持兼容。

## Open Questions

- 后续 PostgreSQL adapter 使用同步 `psycopg` 还是 async driver，需要在真正引入 PostgreSQL 时单独评估。
- `user_store` 作为核心 store 的迁移顺序，需要在后续 change 中结合认证和 migration 状态设计。
