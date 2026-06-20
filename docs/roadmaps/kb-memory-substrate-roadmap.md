# KB / Memory / 部署底座重构 roadmap

这份文档跟踪 2026-06-20 一轮架构讨论定下的方向:把 KB / memory 数据、ingest 管道、部署拓扑统一到一套"可插拔、消模式"的形态。**目标态见 [target-architecture.md §12](../architecture/target-architecture.md)**;讨论结论的可视化(KB 全链路时序图 + 配置归属图)见会话 artifact。本文是从现状到目标的**变更序列 + 进度**。

> ⚠️ 大部分是**方向**,尚未实现。落地经 OpenSpec change,按下方 Phase 顺序。

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
| `kb-worker` | ✅ landed (`f24ae882`) | `fleetent kb-worker` 唯一消费者/单一写入方;移除过渡 drain;admin sync = 入队+轮询(`_wait_for_kb_ingest_job`) | kb-ingest-queue |
| `kb-worker-config-file` | ✅ landed (`b8db5197`) | `$FLEETENT_HOME/kb-worker/.env`(队列/底座/embedder/Vault 接入),平行 node-config-file;connector 配置不进 worker | kb-worker |

落地形态:多触发器 → DB 队列 → 唯一 kb-worker → ingest 核;队列经 `db.py` 边界、worker 不 import platform;明文凭据不入队(只写 `cred_ref`,运行时按 ref 解析留 Phase B)。**单机 ingest worker 链已齐**(target-architecture §12 的单机形态)。

### Phase B — 可插拔数据底座(blocked 占位,分布式才展开)

| change | 状态 | 内容 | 触发判据 |
| --- | --- | --- | --- |
| `agent-data-substrate-pluggable` | blocked 占位 | 底座后端抽象(本地文件↔网络 DB)+ 网络后端实现 + `connector-cred-job-ref`(运行时按 ref 从 Vault 解析) | 部署真走分布式(agent 与 ingest 不再共享文件系统) |

> 取代了旧的 `knowledge-base-standalone-service` 占位:本轮把"KB 升格独立服务"重构成"可插拔底座 + kb-worker"(retrieval 留 agent、management 留 platform、store 进可插拔底座),不再需要 bespoke KB 服务。旧占位已移除。
> 最重、纯重构;展开时可能按数据族(KB/memory/sessions/向量)细分多个 change。向量底座已部分可换 Qdrant,减一点量。

### Phase C — 部署拓扑收敛(接近时再写)

| change | 状态 | 内容 |
| --- | --- | --- |
| `node-launches-agent-single-host` | 未写 | 单机也经 node 拉起 agent(统一);production 不再直起。`fleetent agent run` 保留为 node 用的原语(也可 dev 直跑) |
| `remove-standalone-deployment` | 未写 | 砍 standalone 部署、platform 始终在场;**改 AGENTS.md「agent 必须能在无 platform 环境运行」那条不可逾越规则措辞**(解耦契约部分不变);更新 install/docs |

> ⚠️ AGENTS.md 那条不可逾越规则的措辞**等 `remove-standalone-deployment` 真落地时才改**——规则随代码改,不提前(现在代码仍强制 standalone 可运行)。

## 两条路径

- **到单机目标态** ≈ Phase A(3)+ Phase C(2)= **5 个 change**(底座留本地文件,不碰 B)
- **再到分布式** ≈ + Phase B(可插拔底座 + 凭据 job-ref)

## 依赖图

```
链 A:  kb-ingest-queue → kb-worker → kb-worker-config-file
                              └→ (connector-cred-job-ref,属 B)
链 B:  agent-data-substrate-pluggable(后端抽象 → 网络后端 → cred-job-ref)
链 C:  node-launches-agent-single-host → remove-standalone-deployment
```
链内串行;链间基本独立(connector-cred-job-ref 跨链挂在 kb-worker 之后)。

## 参考

- 目标架构:[target-architecture.md §12](../architecture/target-architecture.md)
- 数据模型:[data-model.md](../architecture/data-model.md)(5 库、per-tenant 物理分区)
- 相关原则:CLI/平台边界(业务走 HTTP、agent 侧治理数据不开平台直写旁路)
