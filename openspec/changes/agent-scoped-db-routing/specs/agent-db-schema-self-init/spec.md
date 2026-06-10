## MODIFIED Requirements

### Requirement: Each agent-side store exposes ensure_schema

`traces.py`, `memory/store.py`, and `reflection.py` SHALL each expose a public
`ensure_schema(db: SQLiteDatabase) -> None` function that creates the store's tables and
indices using `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`（过渡态，后续切片迁入
嵌入式迁移 Y）。`knowledge_base/operations.py` SHALL NOT 再以 `ensure_schema` 自建——KB 关系库 schema
改由 `embedded-schema-migration`（Y）管理（KB 为 Y 首个消费者）。**`session/index.py` 的元数据索引 DB 表
（`sessions` 等运行表）SHALL NOT 再以 `ensure_schema`-into-global 自建**——改经 `agent_scope(tenant, agent_id)`
取 per-agent `agent_state.db` + 嵌入式 Y（session 为继 KB 之后第二个迁出 ensure_schema 的 store）。

#### Scenario: ensure_schema creates tables idempotently

- **WHEN** `ensure_schema(db)` is called on an empty DB
- **THEN** the store's tables and indices are created

#### Scenario: ensure_schema is safe to call repeatedly

- **WHEN** `ensure_schema(db)` is called twice on the same DB
- **THEN** the second call does not raise an error

#### Scenario: session 元数据经 agent_scope + Y 建立

- **WHEN** 初始化某 agent 的 session 元数据索引
- **THEN** 其表经 `agent_scope` 取 `agent_state.db` 后由嵌入式迁移（Y）建立，而非 `session/index.py:ensure_schema` 自建于全局 DB
