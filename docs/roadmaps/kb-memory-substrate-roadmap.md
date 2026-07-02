# KB / Memory / 部署底座重构 roadmap

这份文档跟踪 2026-06-20 一轮架构讨论定下的方向:把 KB / memory 数据、ingest 管道、部署拓扑统一到一套"可插拔、消模式"的形态。**目标态见 [target-architecture.md §12](../architecture/target-architecture.md)**;讨论结论的可视化(KB 全链路时序图 + 配置归属图)见会话 artifact。本文是从现状到目标的**变更序列 + 进度**。

> 进度(2026-06-20):**单机目标态已全部落地**——Phase A(ingest 队列+worker)+ Phase C(砍 standalone)+ B1(底座可插拔抽象 + 本地 SQLite 后端)均已 apply。**只剩 B2(网络后端)占位**,等真走分布式 + 有网络DB环境再实施。

## 当前结论

- **逻辑归属已定,不再纠结**:KB = 派生视图(人策展源、agent 只读+提报告、没人直写 KB、不走 agent 审批门);memory = 真相源(agent 经审批门读写)。
- **统一可插拔数据底座**:memory / KB / sessions / 向量 都是 agent 侧 per-tenant 数据,共用一个底座;单机=本地文件,分布式=网络托管 DB(Postgres/Qdrant,self-hostable)。**memory 与 KB 不各做独立服务**,是同一个"底座后端可插拔"的决定。
- **Ingest = 一个核 + 多触发器 + DB 队列 + 唯一 worker**;**单机也拆 worker**(为消模式/隔离,非扩容)。
- **核心不变量**:agent 永远 node 拉起、ingest 永远 worker、数据永远走 substrate——机制两拓扑一致,只差 **co-location + 后端选择**。
- **部署只两种**:单机 / 分布式,platform 始终在场;砍 standalone **部署模式**,但保留 agent→platform **解耦契约**。

## 已落地的地基(不在本 roadmap 的 delta 内)

- KB 四分(core/retrieval/ingest/management)+ 读写边界护栏
- 审批门统一(`approval_requests` 单一真相源 + `approval_router` 按 subject_type 分派;reflection 复用 permission_gate 外呼)
- node 注册表 / desired-state API / supervisor / secret 注入
- `node-config-file`(node 从 `$FLEETENT_HOME/node/.env` 加载)— ✅ 已落地

## 变更序列

### Phase A — Ingest 队列 + worker(✅ 全部落地 2026-06-20)

到单机目标态的核心。三个 change 一条链,**已全部 apply 落地 main**:

| change | 状态 | 内容 | 前置 |
| --- | --- | --- | --- |
| `kb-ingest-queue` | ✅ landed (`e1997237`) | DB 背 `kb_ingest_jobs`(管理库 Alembic,迁移 099)+ 入队 + 原子 claim/done/retry;触发器停止控制面内联跑 ingest;worker 落地前留过渡 drain | — |
| `kb-worker` | ✅ landed (`f24ae882`) | `fleetent kb worker` 唯一消费者/单一写入方;移除过渡 drain;admin sync = 入队+轮询(`_wait_for_kb_ingest_job`) | kb-ingest-queue |
| `kb-worker-config-file` | ✅ landed (`b8db5197`) | `$FLEETENT_HOME/kb-worker/.env`(队列/底座/embedder/Vault 接入),平行 node-config-file;connector 配置不进 worker | kb-worker |

落地形态:多触发器 → DB 队列 → 唯一 kb-worker → ingest 核;队列经 `db.py` 边界、worker 不 import platform;明文凭据不入队(只写 `cred_ref`,运行时按 ref 解析留 Phase B)。**单机 ingest worker 链已齐**(target-architecture §12 的单机形态)。

### Phase B — 可插拔数据底座(B1 ✅ 已落地;B2 占位)

| change | 状态 | 内容 | 前置/触发 |
| --- | --- | --- | --- |
| `substrate-backend-abstraction`(B1) | ✅ landed (`2ff2a1b9`) | db.py 开库边界做可插拔后端抽象(`BaseSubstrateBackend` + `SubstrateCapabilities` + `create_substrate` 按 URL scheme 选);本地 SQLite=默认实现、行为零变化;agent 侧关系库(agent_state〔含 agent memory〕/kb)经工厂开库(tenant_router 收口);管理库未纳入(随 B2) | — |
| `network-substrate-backend`(B2) | blocked 占位 | 在 B1 抽象下加 Postgres/Qdrant 网络后端 + `connector-cred-job-ref`(运行时按 ref 从 Vault 解析);postgres scheme 现在工厂里是 "not supported yet",B2 把它换成真实现 | 部署真走分布式 + 有网络DB/多机环境可端到端验证 |

> 由旧的合并占位 `agent-data-substrate-pluggable` 拆来(B1 转真已落地、B2 留占位);更早的 `knowledge-base-standalone-service` 占位已移除(本轮把"KB 升格独立服务"重构成"可插拔底座 + kb-worker",不需 bespoke KB 服务)。
> B1 单机就有价值(数据层边界清、SQLite 零变化、为 B2 留干净挂载点);B2 最重、无分布式环境前不实施。

### Phase C — 部署拓扑收敛(✅ 已落地 2026-06-20)

| change | 状态 | 内容 |
| --- | --- | --- |
| `remove-standalone-deployment` | ✅ landed (`7dd04f54`) | 砍 standalone 部署模式、platform 始终在场、node 永远拉起 agent;`fleetent agent run`/`init` 保留为 node 原语+dev(**未删**);改 AGENTS.md 规则措辞(解耦契约「单向不可逆」**原样保留**);install-agent.sh repurpose 为 agent-host(node) installer;docs/§12 同步 |

> 原计划的 `node-launches-agent-single-host` 已**吸收进本 change**——`retire-inmemory-controller` 后 node 已是唯一 launcher,无独立工作可做。

## 两条路径

- **到单机目标态** ≈ Phase A(3)+ B1(1)+ Phase C(1)= **5 个 change,✅ 已全部落地**(底座留本地 SQLite 后端)
- **再到分布式** ≈ + B2(`network-substrate-backend`:网络后端 + 凭据 job-ref)

## 依赖图

```
链 A:  kb-ingest-queue → kb-worker → kb-worker-config-file          ✅ 全落地
链 B:  substrate-backend-abstraction(✅ B1) → network-substrate-backend(B2 占位 + connector-cred-job-ref)
链 C:  remove-standalone-deployment ✅(已吸收 node-launches-agent-single-host)
```
链内串行;链间基本独立。单机目标态(A + B1 + C)已全落地;只剩 B2 等分布式环境。

## 参考

- 目标架构:[target-architecture.md §12](../architecture/target-architecture.md)
- 数据模型:[data-model.md](../architecture/data-model.md)(5 库、per-tenant 物理分区)
- 相关原则:CLI/平台边界(业务走 HTTP、agent 侧治理数据不开平台直写旁路)
