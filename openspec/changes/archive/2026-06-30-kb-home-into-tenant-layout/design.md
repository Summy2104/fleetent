## Context

standalone KB 服务(`kb-serve` / `kb-worker` / `kb-service init-config`)当前把自己的 home 开在 `<FLEETENT_HOME>/kb-service/<tenant>/`(`service_init_config._tenant_home_dir`),内部 `data.home` 默认 `./data` 落 `kb-service/<tenant>/data/{kb.db,kb_vectors.db,kb_ingest_queue.db}`。而 agent 运行时经 `tenant_router` 读的是 tenant-first 布局 `tenants/<tenant>/kb/{kb.db,kb_vectors.db}`(`paths.tenant_kb_dir`)。单机部署下两者是不同物理文件——service 灌的库不是 agent 读的库。

`docs/architecture/agent-home-layout.md` 的目标态本就把 KB 归 `tenants/<tenant>/kb/`,但 standalone service 那条线在 `kb-standalone-ingest` spec 里被显式钉成独立的 `kb-service/<tenant>/` 且 "SHALL NOT 出现 tenants/kb 中间层"。本变更收口这条毛刺:把 service home 收进 tenant 足迹,并让 service 写入即 agent 读取。

约束:KB 尚未接通真实数据(greenfield,无存量迁移);AGENTS.md 解耦契约不变(KB 是 agent 侧独立组件,不 import platform);node 容器 RO 挂载是既有机制,需维持 WAL 一致性。

## Goals / Non-Goals

**Goals:**
- standalone KB service home 收进 `tenants/<tenant>/kb/`,布局与 agent home 同构(配置在根、数据在 `data/`)。
- service 写入的 `kb/data/kb.db` 与 agent retrieval 读取的库是同一物理文件。
- node RO 挂载收窄至 `kb/data/`,把 `.env`(KB secret)挡在 agent 读面外。
- 删除 `kb-worker` 的 tenant-less legacy 配置兜底。

**Non-Goals:**
- 不写存量数据迁移 shim(greenfield)。
- 不动 platform 托管 ingest(已退役)。
- 不改 KB 检索/分块/connector 逻辑、不改 management.db schema。
- 不重命名配置文件 / CLI 命令 / provider id。

## Decisions

**D1 — 配置面与数据面在 `kb/` 下分层(配置在根,数据在 `data/`)。**
`tenants/<tenant>/kb/` 根放 `kb-service.yaml` + `.env`;`kb/data/` 放 `kb.db` / `kb_vectors.db` / `kb_ingest_queue.db`。
- 为何:与 agent home(`agents/<id>/agent.yaml` + `.env` + `data/`)同构,心智统一;且让 node 能"只挂数据面、不挂配置面"。
- 备选:全部平铺在 `kb/` 根(被否:secret 会随 RO 挂载进 agent);数据平铺、配置进子目录(被否:与 agent home 不对称,且用户已定 data 进 `data/`)。

**D2 — node RO 挂载点从整个 `kb/` 收窄为 `kb/data/`。**
`node/backend.py` 的 `_bind_mount(ensure_tenant_kb_dir(...), read_only=True)` 改挂 `kb/data/`。
- 为何:`.env` 在 `kb/` 根、不在 `kb/data/`,挂 `data/` 即天然隔离 secret;`-wal`/`-shm` 与 `kb.db` 同在 `data/`,整挂 `data/` 仍带得上,一致快照不回归。
- 备选:仍整挂 `kb/`,靠文件权限挡 `.env`(被否:RO 挂进容器后仍可读,违反数据主权);只挂具体 db 文件(被否:挂载项随新增文件易漏,且 `-wal`/`-shm` 维护脆)。

**D3 — `data.home` 默认值 `./data` 不变,靠 home 锚点位移自然落位。**
`service_config.load_kb_service_config` 已把相对 `data.home` 解析为相对配置文件父目录。配置文件从 `kb-service/<tenant>/kb-service.yaml` 移到 `tenants/<tenant>/kb/kb-service.yaml` 后,`./data` 自然解析为 `tenants/<tenant>/kb/data/`。
- 为何:改动最小,模板与配置语义不变,只移 home 锚点。

**D4 — `paths.py` 新增 `tenant_kb_data_dir(tenant) = tenant_kb_dir(tenant)/"data"`;`tenant_kb_dir` 仍指 `kb/`(配置 home)。**
读点(`tenant_router.ensure_tenant_kb_dir`、`node/backend._prepare_tenant_kb` + 挂载)统一改用 `tenant_kb_data_dir`。
- 为何:单一派生源,`kb/` 与 `kb/data/` 两个语义各有显式 helper,调用点不再手拼 `/ "data"`。

**D5 — 删除 `worker.load_config()` 的 tenant-less legacy 兜底,而非 repoint。**
- 为何:canonical 入口是 per-tenant `--config`;保留一个 tenant-less 路径(`kb-service/.env` 或 repoint 到 `tenants/default/kb/.env`)本身又是新毛刺。greenfield 无存量,直接删最干净。
- 备选:repoint 到 `tenants/default/kb/.env`(被否:硬编码 default、又引一条隐式路径)。

## 模块边界影响(AGENTS.md 必填)

- **owning package**:`knowledge_base/`(service_init_config / worker / service_config)、`node/`(backend 挂载)、顶层 `paths.py` / `tenant_router.py`(基础设施边界层)。
- **public API surface**:`paths.tenant_kb_data_dir`(新增);`tenant_router.ensure_tenant_kb_dir`(返回路径下移至 `kb/data/`,签名不变);`service_init_config.{plan,apply}_init_config`(目标路径变,签名不变)。CLI 命令面不变。
- **owned tables**:无(不动任何 schema;KB 嵌入式 forward-only 迁移与 management.db 均不触碰)。
- **config namespace**:`kb-service.yaml` 结构不变;`data.home` 默认值不变;无新增 env key。
- **cross-module dependencies**:维持 `knowledge_base/` 与 `node/` MUST NOT `import fleetent.platform.*`;读写边界 `knowledge_base.retrieval` MUST NOT import `knowledge_base.ingest` 不变。
- **migration / shim plan**:无(greenfield,无存量数据)。

## Risks / Trade-offs

- [`kb_ingest_queue.db` 落 `kb/data/` → 随 RO 挂载对 agent 只读可见] → 可接受:它是运营队列、非 secret、只读;若后续要彻底隔离,可单独把队列移出 `data/`,本变更不做。
- [node 挂载点变更若漏改某处仍挂旧 `kb/`] → 集成/e2e 用例断言挂载 `source` 指向 `kb/data/`;`tenant_router` 与 `node/backend` 两处统一走 `tenant_kb_data_dir` helper,减少手拼路径。
- [`paths.tenant_kb_dir` 的既有调用者若期望库直接在 `kb/` 根] → 全量 grep `tenant_kb_dir` 调用点(`tenant_router`、`node/backend`),逐一确认读 db 的改走 `tenant_kb_data_dir`,只取目录的保留。
- [文档多处引用旧 `kb-service/<tenant>/` 路径] → 文档与 Makefile 路径在 tasks 内逐文件改;`test_deployment_docs` / `test_makefile_deploy_targets` 兜底防漂移。

## Migration Plan

greenfield,无数据迁移。部署侧:`fleetent kb-service init-config --tenant <t>` 直接在新位置 `tenants/<t>/kb/` 生成;dev 起栈(Makefile / `.fleetent-dev`)随 init-config 锚点位移自动落新位置。回滚=还原本变更 commit(无持久化副作用)。

## Open Questions

无。所有布局决策(合一 / 配置-数据分层 / 挂载收窄 / 删 legacy 兜底 / 保留命名)已在 brainstorming 中与用户确认。
