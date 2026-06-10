## Why

持久层 roadmap #3（五库物理分离）的地基切片 **3a**。今天 agent 侧库表全靠 `ensure_schema()` 的 `CREATE IF NOT EXISTS` 自建、连接靠各处直连全局 `fleetent.db`，无任何"按主体路由到不同物理库"的能力——这挡住了 #3 的物理隔离（合规硬要求，data-model §5.7）与"可换后端接住 PG/RLS"的目标。3a 先立两块可复用地基（**租户作用域路由** + **嵌入式迁移引擎**），并以 **KB 为第一消费者**验证，为 3b（per-tenant fan-out）铺路。范围与决策已由 B2 协调锁定（data-model.md §6「B2 协调」+ §5.1/§5.2/§5.6/§5.7）。

## What Changes

- **新增租户作用域路由**：`scope(tenant) → {KB 关系 db, KB 向量后端}` 的抽象；调用点只表达"在 tenant X 作用域里访问"，后端可插拔。当下 SQLite 后端路由到 `<tenant>/` 目录文件，**单主体 `default` 先**（多主体 fan-out 留 3b）。
- **新增嵌入式 forward-only 迁移引擎（Y）**：有序 `MIGRATIONS = [(ver, sql)]` + `PRAGMA user_version` 戳 + migrate-on-open + 版本闸（库版本 > 代码已知版本则拒启动）；空库与旧库同一代码路径。一个共享引擎，各库供自己的迁移清单。
- **KB 成为 Y 的第一个消费者**：把 `knowledge_base/operations.py` 的 `ensure_schema()` DDL 原样 lift 成 KB 的 `MIGRATIONS`（v1..vN）；**保留 `tenant_id`/`kb_id` 列**（可换后端接缝：文件路由忽略、RLS 后端按行强制用之，data-model §5.7）。
- **KB 内容存储构造走路由**：所有 `KnowledgeStore` 构造 + `knowledge_base/operations.py` 的 `create_database(_settings().database_url)` 自连接旁路改由路由供连接（它们服务 KB 内容表 knowledge_bases/documents/chunks，绕过注入抓全局库、物理分库后会连错库）。**`knowledge_base/bindings.py` 不在本切片**——它服务绑定表 `knowledge_base_agent_bindings`（alembic 012、`retrieval/scope` 经它解析 agent→KB），整摊归兄弟切片 3a-binding。
- **向量家族路由整改**（§5.6）：`VectorFamily` 显式枚举 + 单一 `family_of()` 路由入口，禁 ad-hoc `startswith`、未知前缀 raise；KB 关系库与向量库由**同一个 tenant-scope** 驱动，避免"只路由关系库、向量仍走扁平串"的半路由返工。

不在本切片（明确排除）：per-tenant 目录 fan-out / 多主体（3b）；platform 只读投影（3b）；agent↔KB 绑定 materialize 进 agent.yaml（兄弟切片 3a-binding——**含 `bindings.py`、`retrieval/scope` 的绑定解析、`knowledge_base_agent_bindings` 表，3a 一律不碰**）；memory/traces 等其余 agent 侧库迁到 Y（后续，3a 只立引擎 + KB 首个消费者）。

## Capabilities

### New Capabilities
- `tenant-scoped-db-routing`: 按主体作用域把 DB 访问路由到可插拔后端（今 SQLite per-tenant 文件、将来 PG per-DB / RLS）；KB 关系库 + 向量库经同一作用域取得后端；agent 侧 store 构造从路由获取连接，禁模块自连全局库。
- `embedded-schema-migration`: agent 侧库的 forward-only 嵌入式迁移引擎（有序迁移步 + `user_version` 戳 + migrate-on-open + 版本闸），取代 per-store `ensure_schema`；KB 作首个消费者。

### Modified Capabilities
- `vector-store`: 「Namespace helpers」由自由字符串工厂升级为 `VectorFamily` 枚举 + 单一 `family_of()` 路由（显式家族、未知前缀拒绝）；KB 向量经同一 tenant-scope 路由。
- `agent-db-schema-self-init`: 嵌入式迁移（Y）取代已迁移库的 per-store `ensure_schema`（KB 首个）；「ensure_schema 与 alembic 漂移护栏」降级为**过渡件**（agent 表脱离 `fleetent.db` 前防漂移，data-model §5.2）。

## Impact

- **代码**：新增路由/作用域模块 + Y 引擎（基座 `db.py` 邻近）；`vector_store/`（namespaces → family 路由）；`knowledge_base/`（core/store 连接来源、operations/bindings 去自连接、KB MIGRATIONS 清单）。
- **数据/schema**：KB 关系库 schema 由 ensure_schema 改为 Y 管（DDL 不变、保留 tenant_id/kb_id 列）；**上线前不迁移数据**（新 schema 全新建，data-model §6）。
- **约束遵守**：agent 侧库走嵌入式 Y、**非 alembic**（管理库仍 alembic-only）；不得 `import fleetent.platform.*`；统一经 `db.py` runtime / store 边界，不扩散裸 `sqlite3.connect`；SQL 用 named parameters。
- **依赖文档**：data-model.md §5.1/§5.2/§5.6/§5.7/§6、target-architecture-proposal.md §4/§5。
