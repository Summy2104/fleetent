# 持久层重设计 —— 决策记录（rationale）

> 记录 fleetent 持久层重设计（#1–#4，2026-06）的**为什么**。现状（as-built）见 [`architecture/data-model.md`](../../architecture/data-model.md)；本文只保留 rationale、决策依据与执行历程，供"为何这样设计"的回溯。所有 change 已合并 main 并归档于 `openspec/changes/archive/`。

## 背景与起因

重设计前的现状暴露三类问题（2026-06 审计，4 个 Explore agent 代码核实 ~50 表）：
- **schema 双权威漂移**：部分表由 Alembic 建、部分由 store `_init_db()` 运行时建（`users`/`audit_log`/`im_connectors`/`api_keys`/`sessions` 等不在 alembic）→ `alembic upgrade head` 从空库只建半套。
- **会话数据 split-brain**：`sessions` 在 `users.db`、`session_meta` 在 `fleetent.db`，名实不符。
- **解耦契约被违反**：agent 运行时写 platform 管理表（`session_meta` 反例）、`user_store.authenticate` import platform（#1 泄漏）。
- **多租户是幻影**：`tenant_id`/`team_id` 裸列贯穿各表，无 `tenants`/`teams` 根实体。
- **迁移链误判更正**：早期以为"迁移链坏了"，实为 `migrations/env.py` 忽略 `DATABASE_URL`、命令误打偏离历史的 dev 库——非迁移代码问题（#1 修 env.py 读 `DATABASE_URL`）。

## 核心决策

### D1 五库物理拓扑（逻辑 4 层 / 物理 5 库类型）
管理库（alembic 单库）/ per-agent 运行库 / 共享记忆库 / KB 关系库 / 向量底座。依据：
- **管理库 ≠ agent 库（物理分开）= 解耦契约的 DB 层落实**：agent 物理上打不开管理库，无法写管理表，根治 #1 泄漏 / session_meta 越界；platform 只读 agent 库。
- **per-agent 库**：隔离、爆炸半径小、单机/受管同布局、SQLite 写不互锁、删 agent = 删目录。
- **共享层按写者再拆（R2-叉1）**：`shared_memory` 是多 agent 写的真相源、KB 是 ingest 单写/agent 只读的派生视图——两类写者/生命周期不混，各自成库（单一写者-类）。

### D2 多租户 = 物理 per-tenant 隔离（tenant=主体）
- 客户存在多法人主体（A/B），主体间数据（财务 KB/记忆/会话）**必须强隔离**——合规/数据主权硬要求。
- **物理 vs 逻辑重估 → 保持物理**：① 合规需结构性保证；② SQLite 无 RLS，逻辑隔离只能纪律级（漏一个 `WHERE tenant_id` 即泄漏）；③ 个位数主体，物理成本可忽略；④ per-agent 本就物理，tenant 物理只是加目录前缀；⑤ 财务数据住共享/KB 层，最不该纪律级。
- **立实体**：`tenants`(=主体) / `teams`（其下）/ `users.tenant_id`；**v1 不建 `team_members`**（全仓无处读"用户的 team"，共享记忆/KB/审批都走 **agent 归属 team** `agents.team_id`）。
- **实现成"租户作用域边界 + 可换后端"**：调用点只说"在 tenant X 作用域"，后端可插拔（今 SQLite per-tenant 文件；将来 PG per-tenant DB 换 DSN，或 RLS 单库按行强制，调用点不动）。团队已规划上 PG。
- **agent 侧表保留 `tenant_id` 列（不删）**：文件路由忽略它、**RLS 后端按它做行级强制**——它是"可换后端"接缝。代价为零。**与 memory 删 namespace 分道**：per-agent 隔离无 RLS 未来，tenant 有。

### D3 双 schema 权威：管理库 Alembic / agent 侧嵌入式迁移（Y，R2-叉3）
- 仅**管理库 alembic-only**（管理表只在受管模式存在 → 单一权威、不漂移）。
- **per-agent / 共享记忆 / KB 关系库走嵌入式 forward-only 迁移（Y）**：schema 定义在代码（有序 `MIGRATIONS=[(ver,sql)]`）、DB 只存 `PRAGMA user_version`、migrate-on-open、每文件自迁、版本>代码则拒启动。原因：单机 agent 须脱离 alembic 启动；N 个动态建的 per-tenant 文件不能跑中央 alembic。
- 关键工程约束：**一个物理文件一个 `user_version` → 由一份统一 MIGRATIONS 列表管**（`agent_state.db` 的 sessions/traces/reflection/memory/approvals 全在 `runtime/agent_state_migrations.py` 一份列表，单调版本；不能每 store 各一份跑同文件，否则撞戳/`SchemaTooNewError`）。
- 过渡件：#1 立的"ensure_schema↔alembic 漂移护栏"在 agent 表脱离 `fleetent.db` 后退役。

### D4 向量 = 独立 substrate（模型 A），17 库计数
- 向量经 `vector_store`（横切 infra，非 KB 子件）的**独立后端/文件**，**不寄居关系库**——否则无法单独把向量层换 Qdrant（破坏可换后端）。
- 按 namespace 家族路由：`mem:`→per-agent 向量库、`shared:`→共享记忆向量库、`kb:`→KB 向量库。per-agent 记忆向量必须 per-agent（否则隔离在向量层是假的）。
- **计数**：2 主体 × 各 2 agent = **17 库**（管理 1 + 每主体〔2 agent×(关系+向量)=4 + 共享 2 + KB 2〕×2）。"物理 5 库"是**类型数**非文件数。
- 命名约定：`X.db`/`X_vectors.db` 配对，per-tenant 层 `X`=资源（`kb`/`shared_memory`），per-agent 层 `X`=归属（`agent_state`，避免撞 runtime 引擎/agent 定义）。
- 并发前提：所有 SQLite 连接 WAL + busy_timeout（关系库 `db.py`、向量库 `vector_store/backend.py` 同值 5000ms）——支撑 platform 只读投影读 + agent 写、共享记忆多 agent 写。

### D5 审批 = agent 全权能力，platform 只读下游投影（R1）
- agent 撞风险门 → 查审批人路由 → 经 im_gateway **主动私信**审批人 → 阻塞等结果 → 写 agent 侧产物。**请求者 ≠ 审批人**。
- **承重假设**：platform 不能同步 gate、不能事后回拦 agent 本地已批准执行的动作；中央治理只在**配置时**表达（agent.yaml / allowlist / agent_policy 白名单）。这是"agent 必须脱离 platform 跑"唯一自洽的模型。
- approvals 真相源在 **per-agent `approval_store`**；agent 侧只存**不透明 actor 标签**，platform 投影时 join 真实身份（经 Identity）。审批人解析链：`agent.team_id 审批人 → tenant 审批人 → reject`（default-closed），部署时 materialize 进 agent.yaml。
- **copy-up 语义按真相源/派生视图分叉**：user-memory/shared-memory/skill = 真相源（经门直接写）；KB = 派生视图（不直接写，走 curated 源 → sync 重建）。

### D6 Identity 端口（#4）
authn 抽基座端口（凭证→`Principal{user_id,tenant_id}`）：认证属 edge、核从不认证只消费 Principal；agent 侧解析器不 import platform → 结构性根除 #1 泄漏。详见 target-arch §6（rationale 另见 memory `identity-auth-model`）。

### D7 v1 实体减法
砍/外置（"逻辑实现了但生产没接线"的半成品，按"有无真路由/调用点"核实）：
- **砍**：askit 三表（DEAD）、`invites`（自助注册不可达）、2FA（半成品）、`knowledge_base_agent_bindings`（死孤儿，见 §4-④ 收敛）。
- **descope**：`quotas`/`quota_usage`（check/record 零调用）。
- **外置**：自建 fleet 监控（alert_rules/alerts/metric_samples/maintenance_windows）→ Prometheus/Grafana。
- **保留**：知识图谱（检索零用但留未来）、自进化套件、session_anti_flap、sub_agent_runs、KB 同步态。
- **defer**：`connectors.agent_id`（与 MCP scoping + client_secret 安全保证纠缠）。

### §4-④ agent↔KB 绑定收敛（一活一死）
不是"两张并行表"，而是 `agent_kbs`（活、唯一真相源、admin 写带审计、materialize 进 `agent.knowledge` 供 retrieval 读）+ `knowledge_base_agent_bindings`（死孤儿、无写入点）。收敛 = 纯清理（drop 死表 + 删死 resolver），由 `drop-dead-kb-binding-path` 落地。

## B2：KB 模块四分 ↔ #3 物理库协调
KB 四分（core/retrieval/ingest/management，已落地、`retrieval ✗→ ingest` 有 unit test 强制）与 #3 KB 物理库对齐。核心发现：`KnowledgeStore(database)` 是构造注入连接 → #3 租户路由从此插、core/store 零改。3a = 路由+Y+KB MIGRATIONS+向量家族整改；3a-binding = 绑定 materialize；3b per-tenant fan-out + 只读投影。

## 执行历程与节奏
| 阶段 | 内容 | change |
|---|---|---|
| #1 | env.py 读 DATABASE_URL + 漂移护栏 + 消灭 users.db | `persistence-hygiene` |
| A | 审批重设计（R1） | `agent-owned-approval` |
| #2 / #2.5 | 管理表收编 alembic / 立 tenants·teams·users.tenant_id | `mgmt-tables-into-alembic` / `establish-tenancy`（067-070） |
| #3 | 五库物理分离 | `sqlite-wal-concurrency` · `vector-backend-wal-concurrency` · `tenant-scoped-db-routing`(3a) · `drop-dead-kb-binding-path` · `agent-scoped-db-routing`(3b-1) · `per-agent-traces-reflection-lib`(3b-2) · `per-agent-memory-lib`(3b-3) · `per-agent-approvals-lib`(3b-4) · `shared-memory-lib`(3c) · `multi-tenant-fanout-projection`(3d) |
| #4 | Identity 端口 | `identity-port` |

**节奏经验**：detailed spec **即时生成**（反映落地时真实代码）、**串行推进**、**逐片复核下游**（每片落地后核对并修正后续 spec）——多次避免返工（如 3b-2 落地暴露"统一 MIGRATIONS 列表"约束、3d 落地暴露"只读 open 不得 migrate"、3d 归档误把 delta 覆盖进 canonical spec 等，均在复核时捕获修正）。

关联 memory：`persistence-redesign-roadmap`、`v1-entity-subtraction`、`approval-flow-agent-owned`、`identity-auth-model`、`openspec-slice-scope-final-review`。
