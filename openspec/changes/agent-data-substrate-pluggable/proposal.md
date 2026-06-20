> **状态:占位 / BLOCKED — 仅登记范围,不在当前批次实施。** 终局形态(分布式拓扑)需要时再展开;现阶段单机用本地文件底座已足够。详见 [target-architecture.md §12](../../../docs/architecture/target-architecture.md)。

## Why

target-architecture §12 的"统一可插拔数据底座":memory / KB / sessions / 向量 都是 agent 侧 per-tenant 数据,共用一个底座。**单机=本地文件**(现状),**分布式=网络托管 DB**(Postgres/Qdrant,self-hostable)。当部署真正分布式(agent 与 ingest/写入方不再共享文件系统)时,需要把底座后端抽象成可插拔接口、并实现网络后端。**在那之前,本 change 不实施**——单机本地文件最简单、也最对。

## What Changes（占位,不在本批实施）

- **底座后端抽象**:为 agent 侧数据存储(KB 关系 / memory / sessions;向量底座已部分可换 Qdrant)定义统一后端接口(类似 sandbox backend 的可插拔模式),本地文件 = 默认实现。
- **网络后端实现**:Postgres + Qdrant 等网络托管后端,经配置选型;数据不出内网(self-hostable)。
- **连带**:`connector-cred-job-ref`(job 带凭据 ref、worker 运行时按 ref 从 Vault 解析)——分布式下 secret 不在队列 at-rest 的配套。

## Capabilities

### New Capabilities
<!-- 待终局形态(分布式)决策后定义;可能拆为:底座抽象 / 网络后端 / 各数据族适配 多个 change -->

## Impact

- **BLOCKED ON / 前置**:Phase A(`kb-ingest-queue` → `kb-worker` → `kb-worker-config-file`)落地;且部署形态真正走向分布式(agent host ≠ ingest/写入方 host)。
- **触发判据**:agent 与 ingest 不再共享文件系统(单机→分布式)。单机/standalone-dev 永远保留本地文件后端。
- **可能拆分**:底座抽象(大·纯重构)/ 网络后端实现(大)/ `connector-cred-job-ref`(中)——展开时按数据族细分。

## 待讨论决策点（远期）

1. 后端接口的粒度:一个统一 substrate 接口,还是按数据族(KB/memory/sessions/向量)各自后端?
2. 网络后端选型与连接管理(连接池、多租户路由、迁移在网络 DB 上怎么跑)。
3. 与现有"嵌入式 forward-only 迁移"(per-tenant 文件)如何在网络后端下共存/迁移。
4. `connector-cred-job-ref` 的 Vault 接入模型(worker principal 的授权范围)。
