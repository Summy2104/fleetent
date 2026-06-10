## Context

持久层 roadmap #3 把单 `fleetent.db` 拆成五物理库、按主体物理分区（data-model §5.1/§5.7）。3a 是其地基切片：先立**租户作用域路由**与**嵌入式迁移引擎（Y）**两块可复用基座，以 KB 为第一消费者验证，单主体（`default`）先。

现状（B2 测绘，已核实）：
- KB 模块四分（core/retrieval/ingest/management）**已落地**，`retrieval ✗→ ingest` 由 unit test 强制（`tests/unit/test_module_dependency_guardrails.py`）。
- `KnowledgeStore(database: SQLiteDatabase)` 是**构造注入连接**；但 `bindings.py`/`operations.py` 另有两条 `create_database(_settings().database_url)` 自连接旁路绕过注入。
- KB schema 由 `operations.py:ensure_schema()` 的 `CREATE IF NOT EXISTS` 自建（迁移注释 006-046），**非** alembic、**非** 结构化迁移。
- agent 侧库全仓**无 `user_version` 风格结构化迁移**（Y 是 greenfield）。
- 向量 namespace 是自由字符串工厂（`mem:`/`shared:`/`kb:`），**无** `VectorFamily` 枚举 / `family_of()` 路由。

约束：agent 侧库走嵌入式 Y、非 alembic（管理库仍 alembic-only）；不得 `import fleetent.platform.*`；统一经 `db.py` runtime/store 边界；SQL named parameters；上线前不迁移数据。

## Goals / Non-Goals

**Goals:**
- 立"租户作用域 → 可换后端"抽象：调用点只说"在 tenant X 作用域里访问"，后端可插拔（今 SQLite per-tenant 文件、将来 PG per-DB / RLS）。
- 立共享 Y 迁移引擎：有序迁移步 + `user_version` + migrate-on-open + 版本闸；空库/旧库同一路径。
- KB 接入两块基座：连接走路由、schema 走 Y（DDL 原样 lift、保留 tenant_id/kb_id 列）；清两条自连接旁路。
- 向量家族路由整改（§5.6），与关系库共用同一 tenant-scope。

**Non-Goals:**
- 多主体 per-tenant 目录 fan-out（3b）；platform 只读投影（3b）。
- agent↔KB 绑定 materialize 进 agent.yaml（兄弟切片 3a-binding）。**`knowledge_base/bindings.py`、`retrieval/scope` 的绑定解析、`knowledge_base_agent_bindings` 表本切片一律不碰**——它服务的是绑定（alembic 012、跨 agent/管理边界），与 KB 内容存储（operations/KnowledgeStore，3a 处理）是两摊。
- memory/traces/session 等其余 agent 侧库迁到 Y（3a 只立引擎 + KB 首个消费者）。
- 真实 PG/RLS 后端实现（只立抽象接缝，不落 PG）。

## Decisions

**D1 路由插入点 = `KnowledgeStore(database)` 构造注入。** 路由器负责构造并供给 `SQLiteDatabase`，`core/store` 内部零改动。
- 备选：重构 `core/store` 让它自己按 tenant 开库。否决——把路由职责塞进 store 违背"调用点表达作用域、store 只管 SQL"；且四分已把连接放在构造边界，顺势即可。

**D2 抽象成"作用域 + 可换后端"，不直连 SQLite 路径。** 提供 `scope(tenant)`，返回该作用域的关系 db + 向量后端句柄；SQLite 后端把 `<tenant>/` 目录文件映射进来。
- 备选：各处硬编码 `<tenant>/kb.db` 路径。否决——锁死 SQLite，上不了已规划的 PG/RLS（data-model §5.7）；抽象的成本就是一个间接层，收益是后端可换。

**D3 保留 `tenant_id`/`kb_id` 列（不删）。** 文件路由忽略该列、RLS 后端按它做行级强制——它是"可换后端"的接缝。
- 备选：像 memory 的 `namespace`（R2-叉2）那样删。否决——tenant 有 RLS 未来、memory 没有；删了锁死只能 per-tenant-DB；且 KB 7 表 + 复合 PK + 满屏 `WHERE tenant_id` 大改、churn 重。保留则 schema 几乎不动（换文件、列不动），3a 风险大降。

**D4 一个共享 Y 引擎、各库供自己的 `MIGRATIONS`。** migrate-on-open / `user_version` / 版本闸是通用逻辑，放基座；KB 在 `core/` 供自己的迁移清单。
- 备选：每库各写一套迁移逻辑。否决——重复、易分叉。

**D5 KB 的 Y v1 = 现 `ensure_schema` DDL 原样 lift。** 不借机改 schema。
- 备选：顺手重构 KB schema。否决——3a 要低风险落地基座；schema 设计（§4-①③④）是正交专题。配合"上线前不迁移数据"（新库全新建），v1 一次建到位即可。

**D6 `VectorFamily` 枚举 + 单一 `family_of()` 路由，未知前缀 raise（fail-fast）。** KB 关系库与向量库由**同一** tenant-scope 驱动。
- 备选：保留 ad-hoc `startswith`。否决——§5.6 必做；隐式前缀匹配是 bug 温床、"namespace"一词三重过载需拆。

**D7 单主体 `default` 先，多主体 fan-out 留 3b。** 3a 的 `scope(tenant)` 对 `default` 返回单一后端；抽象到位但不做目录 fan-out。
- 备选：3a 直接做多主体。否决——fan-out 是 3b，3a 先把接缝和引擎立稳、de-risk。

## Risks / Trade-offs

- **自连接旁路漏清 → 连错库**（物理分库后 `create_database(settings)` 抓全局库）。→ 缓解：加护栏测试断言 KB **内容存储**（operations/KnowledgeStore）无 `create_database(...settings...)` 自连接、连接来自路由；红/绿覆盖。**护栏范围不含 `bindings.py`**（绑定模块归 3a-binding，本切片暂留其现状）。
- **Y 版本闸过严锁启动**（库版本 > 代码已知 → 拒启动是有意防降级，但误触会卡）。→ 缓解：仅在"库版本 > 代码"时拒、相等/小于正常迁；测试覆盖空库(v=0 跑全部)、旧库(增量)、超前库(拒)三态。
- **向量家族整改打断现有 namespace**（mem/shared/kb 三家族都在用）。→ 缓解：枚举覆盖三家族 + 各家族路由测试；未知前缀 raise 而非静默兜底（暴露遗漏）。
- **保留 tenant_id 列被误读成死列**。→ 缓解：spec/注释写明它是可换后端/RLS 接缝（§5.7），非冗余。
- **抽象对单主体显得过度**。→ 缓解：3a 的作用域对 `default` 就是直返，抽象层只是接缝、非提前 fan-out；3b 兑现多主体时调用点不动。

## Migration Plan

- **无数据迁移**（上线前内测窗口）：新 schema 全新建，旧 KB 数据丢弃/重新摄取（data-model §6）。
- KB 关系库 schema 经 Y v1 建出（= 现 ensure_schema 的 DDL）；旧 `ensure_schema()` 路径在 KB 迁完后退役（其余未迁库暂留 ensure_schema + 漂移护栏过渡件）。
- **回滚**：3a 全程在 feat 分支；未上线、无生产数据，回滚 = revert 分支。

## Open Questions

- per-tenant 下 KB 向量 namespace 的确切形状：tenant 进文件后用 `kb:{kb_id}`，还是为与关系库列对称保留 `kb:{tenant_id}:{kb_id}`？倾向**保留 tenant_id**（与 D3 对称、可换后端友好），spec/实现时定。
- `<tenant>/` 目录下文件命名（如 `kb.db` / `kb_vectors.db`）——实现细节，apply 时定，不影响 spec 契约。
