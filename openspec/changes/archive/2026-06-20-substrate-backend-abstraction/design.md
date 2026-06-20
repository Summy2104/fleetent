## Context

agent 侧关系库现在直接经 `db.py` 的 `SQLiteDatabase` / `create_database(database_url)` 开;各库自带嵌入式 forward-only 迁移(`agent_state_migrations` / `shared_memory_migrations` / `knowledge_base/core/migrations`)。要让分布式能换网络 DB,先得有可插拔后端抽象。本仓 `integrations/sandbox`(`BaseSandboxBackend` + `BackendCapabilities` + `factory.create_backend` + capability 门控)是现成、已验证的范式,照抄。

## Goals / Non-Goals

**Goals:** 立底座后端抽象(接口 + capabilities + 工厂,按 URL scheme 选);本地 SQLite 后端=默认实现、行为不变;agent 侧三关系库经工厂开库;单机用 SQLite 后端端到端验证。

**Non-Goals:** 不实现网络后端(Postgres/Qdrant)= B2;不改表结构/迁移逻辑;不重写向量底座(已可换,仅对齐位置);不碰 store 业务逻辑(只动"怎么开库")。

## Decisions

### D1:镜像 sandbox backend 范式

`BaseSubstrateBackend`(ABC/Protocol)+ `class SubstrateCapabilities`(flags:`network`/`shared_across_hosts`/`embedded_migrations` 等)+ `factory.create_substrate(database_url)` 按 scheme 分派。消费方按 capabilities 门控、不用 isinstance。与 sandbox 的 `BackendCapabilities`/`create_backend` 一一对应,降低认知成本。

### D2:本地 SQLite 后端 = 现状收编,零行为变化

现有 `SQLiteDatabase` + 嵌入式迁移(migrate-on-open + PRAGMA user_version)整体作为 `SQLiteSubstrateBackend` 的实现;`sqlite://`(及无 scheme 的本地路径)→ 该后端。开库结果、迁移行为、PRAGMA 全不变 → 单机现有 integration 测试应原样通过(回归保护)。

### D3:开库点统一走工厂

per-agent 运行库 / 共享记忆库 / KB 关系库的开库调用(现在散在各 store 的 `_database()`)改为经 `factory.create_substrate(url)`。管理库(Alembic)是否纳入:管理库走 Alembic、是 platform 侧,本 change **可纳入工厂但保持 SQLite 默认**(为 B2 统一);若纳入有风险则 design 留"先只收 agent 侧三库,管理库随 B2"。倾向先收 agent 侧三库(目标态的 per-tenant 底座就是这三库 + 向量)。

### D4:granularity——立抽象 + 一次收编三个关系库

接口一致、风险集中在"开库点"而非各 store 逻辑,所以一次收编 agent_state / shared_memory / kb 三库可控(每库一个 task + 回归测试)。向量底座已有可换层,本 change 只在文档/能力上对齐其"底座成员"身份,不改其实现。

### D5:连接配置

沿用 URL 约定(`DATABASE_URL` 及各 store 路径/URL);本地后端 URL 仍指向 per-tenant 文件路径。kb-worker / agent / memory 的"底座连接"配置(见 kb-worker-config-file / node 配置)填该 URL,本地填 sqlite 路径,B2 时可填 postgres URL——配置形状现在就为 B2 留好。

## Risks / Trade-offs

- **[大重构、触碰多个 store 开库点]** 风险在开库点改动遗漏;每库独立 task + 现有 integration 测试回归保护;SQLite 后端行为零变化是验证基线。
- **[管理库是否纳入]** D3 留弹性;倾向先 agent 侧三库,管理库随 B2,避免一次动太多。
- **[嵌入式迁移与未来网络后端的张力]** 本地后端用嵌入式迁移;网络后端(B2)的迁移模型不同——本 change 把"迁移"作为后端能力之一(capability),接口上留好,实现差异留给 B2。
- **[过度抽象]** 别为 B2 凭空加用不上的接口;抽象以"本地后端能跑 + B2 能挂"为度,接口最小化。
