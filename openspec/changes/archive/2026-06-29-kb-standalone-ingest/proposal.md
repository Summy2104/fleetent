## Why

需求已定:**KB 要能独立于 platform 部署、platform 不在也能完整运作(读 + ingest)**。现状 ingest 的"什么/何时/凭据"都耦合在 platform——连接器配置在 management.db 的 `kb_connectors`、队列在 management.db、sweep 在 platform cron、入队由 platform admin/sweep。这意味着没有 platform 就没有 ingest。

本 change(②b 第一刀)让 **KB 服务自包含 ingest**:连接器/检索/模型/分块配置在 KB 服务**自己的配置文件**,凭据在 **KB 主机本地**(`env:`/`file://`),队列与 worker 在 **KB 主机本地**,sweep 在 **KB 服务自己的调度器**。**加法**——平台托管那套**暂留**(退役放后续一刀 `kb-retire-platform-ingest`,先建新、验证、再退旧,降爆炸半径)。

## What Changes

- **standalone KB 服务配置契约**:新增 `kb-service.example.yaml`(service / data / retrieval / embedding / extraction / chunking / connectors)+ `.env.example`(service key / 模型 key / 连接器凭据)。boot 时**校验**所有 `credential_ref` 指向的 env/file 是否就位,缺则启动即报错。
- **KB 服务从配置文件构造 ingest settings 并注入 operations**(复用 B1 的"operations 吃注入 settings"):连接器定义来自配置文件,不来自 management.db。
- **KB 主机本地队列 + worker + sweep**:worker 抽 **KB 本地**队列(非 management.db);sweep 由 KB 服务自己的调度器按配置文件的 `sync_interval_seconds` 跑;凭据在 KB 主机本地按 ref 解析。
- **platform-optional**:在无 platform、management.db 不存在的环境下,KB 服务仍可按配置文件完成 connector sync / ingest / 检索。

不改变(本刀不碰,留退役刀):平台侧 `kb_connectors` 表、platform sweep cron、management.db 队列、平台 admin 入队路径——**暂留**,平台托管模式仍可用;读 seam(Local/Http)不动;knowledge_base 检索核不动。

## Capabilities

### New Capabilities
- `kb-standalone-ingest`: KB 服务自包含 ingest——配置文件源连接器、本地凭据、本地队列 + worker + sweep、boot 校验、无 platform 也能运作。

### Modified Capabilities
- `knowledge-service-config`: 兑现"standalone Knowledge 服务定义自己的 home 与 config 契约"(原 spec 标记为留给未来 change 的部分)。
- `kb-ingest-worker`: "connector 配置不在 worker 自身配置内" 按部署模式区分——**平台托管**模式 connector 经 job 下发(不变);**standalone** 模式 KB 服务从自己的配置文件持有 connector 配置。

## Impact

- **owning package**:`fleetent.knowledge_base`(配置加载、standalone 队列/worker/sweep、boot 校验)。依赖 `tenant_router` / `identity` / `knowledge_base` public;**不 import platform**(护栏)。
- **public API surface**:新增 standalone 配置契约(`kb-service.yaml` / `.env`)+ KB 服务自有调度;`operations` 仍吃注入 settings(B1)。
- **owned tables**:KB 本地 ingest 队列(KB 主机本地 SQLite,嵌入式迁移或独立文件;**非** management.db)。
- **config namespace**:`kb-service.yaml` 的 service/data/retrieval/embedding/extraction/chunking/connectors;`.env` 的 service/model/connector secret。
- **cross-module 依赖**:`knowledge_base` ✗→ platform 保持;standalone 路径不连 management.db。
- **数据主权**:连接器凭据只在 KB 主机本地(`env:`/`file://`),不上网、不穿区。
- **测试**:integration(配置文件 → 注入 operations → connector sync 写 kb/;本地队列 drain;boot 校验缺 secret 报错;无 platform/management.db 环境下成立)。
- **明确不做(后续 `kb-retire-platform-ingest`)**:退役平台侧 `kb_connectors`/sweep/management.db 队列/入队路径。本刀两套并存(过渡),退役在后。
