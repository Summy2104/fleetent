## Why

target-architecture §12 的"统一可插拔数据底座":memory / KB / sessions 等 agent 侧 per-tenant 数据共用一个底座,单机=本地文件,分布式=网络托管 DB。本 change 做**第一步、也是最大的一步:在开库边界引入可插拔后端抽象**——定义统一接口 + 本地 SQLite 后端(默认实现),按连接 URL scheme 选型。**这一步单机就有价值**(数据层边界更清、为分布式铺路),且**完全可在单机用 SQLite 后端验证**;网络后端(Postgres/Qdrant)是后续 `network-substrate-backend`(B2)。

现成范式:本仓 `integrations/sandbox` 已有成熟的可插拔后端模式(`BaseSandboxBackend` + `BackendCapabilities` + `factory.create_backend`)——本 change 照此为数据层建对应抽象。`db.py` 已有 `create_database(database_url)` 按 URL 建库,本 change 把它升级为"按 scheme 分派后端"。

## What Changes

- **定义底座后端抽象**:`BaseSubstrateBackend`(或等价 Protocol)+ `BackendCapabilities`(声明能力,如 `network`/`shared_across_hosts`)+ 工厂(按 `database_url` scheme 选实现),镜像 sandbox backend 范式。
- **本地 SQLite 后端 = 默认实现**:现有 `SQLiteDatabase` / 嵌入式 forward-only 迁移收编为该后端的实现;`sqlite://` URL → 本地后端。行为与现状一致(可验证)。
- **agent 侧关系库走后端抽象**:per-agent 运行库(`agent_state.db`)、共享记忆库(`shared_memory.db`)、KB 关系库(`kb.db`)的开库统一经工厂获取后端实例,而非直接 `SQLiteDatabase(path=...)`。
- **能力门控**:消费方按 `BackendCapabilities` 门控(如某些路径仅本地后端适用),不用 isinstance(对齐 sandbox 的 capability 门控)。
- **向量底座**:已部分可换(Qdrant),本 change 对齐其在抽象下的位置(不重写),保持现状可用。

## Capabilities

### New Capabilities
- `substrate-backend`:agent 侧数据底座的可插拔后端抽象(接口 + capabilities + 工厂),本地 SQLite 为默认实现。

### Modified Capabilities
- `database-runtime`:开库边界由"直接建 SQLiteDatabase"升级为"按 URL scheme 经工厂选后端";SQLite 仍为默认、行为不变。

## Impact

**owning package**:`src/fleetent/db.py`(工厂 + 抽象)、各 store 的开库调用点(runtime/agent_state、memory/shared、knowledge_base/core);新增后端抽象模块

**public API surface**:无 HTTP;`db.py` 的 `create_database` 语义扩展(按 scheme 选后端,SQLite 默认)

**owned tables**:无 schema 变更(只换"怎么开库",不换表)　**config namespace**:连接 URL(沿用 `DATABASE_URL` 及各 store 的 URL 约定)　**migration**:无(嵌入式迁移收编进本地后端,逻辑不变)

**cross-module dependencies**:抽象层在基座(db 层),被各 agent 侧 store 依赖;**MUST NOT 引入 store→platform 反向依赖**(护栏)。kb-worker / agent / memory 都经抽象开库。

**与 B2 关系**:`network-substrate-backend`(B2,占位)在本抽象下加 Postgres/Qdrant 实现;本 change 只交付抽象 + 本地后端,**单机可端到端验证**,不引入未验证的网络后端。

**granularity 决策(design 详述)**:本 change 是否一次收编全部三个 agent 侧关系库,还是先立抽象 + 收编一个(如 KB)再逐个跟进——见 design;倾向"立抽象 + 全部三个关系库经工厂",因为接口一致、风险在开库点而非各 store 逻辑。
