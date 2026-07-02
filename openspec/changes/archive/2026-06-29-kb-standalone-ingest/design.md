## Context

需求:KB 独立于 platform、platform 不在也能跑(读+ingest)。前置:provider seam(Slice1)+ HttpProvider(Slice①)+ kb-read-service(②a,执行中)已让"读"自包含;kb-data-dir-isolation 已把 KB 数据收进 `tenants/<t>/kb/`。本 change 让"写/ingest"自包含。

现状(探子 a8d5f6c4 + 现场):队列 `kb_ingest_jobs` 在 management.db(`kb_ingest_jobs.py` 用 `Settings().database_url`);worker(`knowledge_base/worker.py`)抽它、经 tenant_router 写租户 kb;连接器配置在 management.db `kb_connectors`;凭据 `credential_ref`(env:/file://,`operations._read_credential_ref`,**connector 级静态、非 per-user**);sweep 在 platform cron。B1 已让 `operations` 吃**注入** settings(本 change 从配置文件构造注入)。

## Goals / Non-Goals

**Goals:**
- standalone KB 服务配置契约(`kb-service.yaml` + `.env`)+ boot 校验。
- KB 服务从配置文件构造 ingest settings 注入 operations(连接器来自文件)。
- KB 本地队列 + worker + sweep + 本地凭据,无 platform/management.db 也能 ingest。

**Non-Goals:**
- 不退役平台侧 `kb_connectors`/sweep/management.db 队列/入队(后续 `kb-retire-platform-ingest`);本刀两套并存(过渡)。
- 不改读 seam、不改 knowledge_base 检索核、不改 connector 同步算法。
- 不做 platform 作为可选管理层的 UI/API(更后)。

## Decisions

### 决策:配置文件 → KnowledgeConfigSnapshot → 注入 operations(复用 B1)
- standalone 启动时加载 `kb-service.yaml`,构造与 `kb_connector_store.as_knowledge_base_settings()` 等价的 snapshot,注入 `operations`。B1 让 operations 只吃注入 settings,所以**两种来源(DB / 文件)对 operations 透明**,无双源违规。

### 决策:KB 本地队列(非 management.db),mode 决定队列后端
- standalone:队列是 KB 主机本地 SQLite(独立文件 / 嵌入式迁移),`kb_ingest_jobs` 的队列逻辑参数化队列连接,使其可指向本地库而非 `Settings().database_url`。worker/claim/done/retry/可观测逻辑**全部复用**(只换队列连接来源)。
- 平台托管:队列仍 management.db(不变)。**部署模式选其一**,本 change 加 standalone 分支,不动托管分支。

### 决策:sweep 进 KB 服务自有调度器
- standalone:KB 服务自己起调度(按配置文件 `sync_interval_seconds`),到期入本地队列。复用现有 sweep 的 due 判定/去重/重试逻辑,只换"读连接器来源(文件)+ 入本地队列 + 自己的定时器"。
- 平台托管:platform cron sweep 不变。

### 决策:凭据本地,connector 级共用
- `credential_ref` 在 KB 主机本地解析(现有 `_read_credential_ref` 即本地 os.environ/file)。多 connector 共用同一 env 名 → `.env` 一条。**真值不上网**(尤其安全分区)。

### 决策:boot 校验
- 启动时枚举所有 connector 的 `credential_ref`,检查 env/file 就位;检查 embedding endpoint 已配。缺失启动即失败、指出缺项(不延迟到运行时)。

### 决策:platform-optional
- standalone 路径不连 management.db;`knowledge_base` ✗→ platform 护栏保持。无 platform/management.db 环境下,ingest/检索按文件配置成立。

## Risks / Trade-offs

- **[过渡期两套并存]** 本刀后平台托管 + standalone 两套 ingest 暂时共存,worker/sweep/enqueue 需按部署模式分支。**Mitigation**:模式是部署级配置(一个部署只走一种);分支点集中、清晰;退役刀收敛回一套。这是"先建新、验证、再退旧"的有意过渡,非永久两模式。
- **[队列参数化触碰核心]** 改 `kb_ingest_jobs` 的队列连接来源。**Mitigation**:只把"连接来源"参数化,claim/done/retry/可观测逻辑不动;integration 覆盖本地队列与 management.db 队列两路。
- **[配置手改错]** 手动 `kb-service.yaml`/`.env` 易错。**Mitigation**:boot 校验 + schema + 好 example;缺项启动即报。
- **[仍依赖 embedding/extraction 端点]** standalone 不依赖 platform,但仍需 embedding(必)/extraction(开图谱时)端点可达。**Mitigation**:boot 校验 embedding;文档说明这是基础设施依赖,非 platform。

## Migration Plan

- 纯加法:新增 standalone 配置契约 + standalone ingest 路径;平台托管路径与 management.db 不动。新部署可选 standalone;存量平台托管不受影响。
- 队列本地库:standalone 首次启动建本地队列库(嵌入式迁移/独立文件)。
- 回滚:删 standalone 入口/还原代码;平台托管路径不受影响。
- 后续 `kb-retire-platform-ingest` 再退役平台侧。

## Open Questions

- 本地队列用独立 SQLite 文件还是并入 `kb/` 下某库:实现时定(倾向 KB 主机本地独立文件,生命周期随 KB 服务)。
- standalone 与 ②a(kb-read-service)是否合进同一 `fleetent kb serve` 进程(读+sweep 同进程)还是 kb-serve + kb-worker 两进程:倾向沿用两进程(读/写负载隔离,见之前讨论),实现时确认。
