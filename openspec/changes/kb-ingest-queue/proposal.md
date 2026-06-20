## Why

KB ingest 当前在 platform 进程内**同步内联**跑(`kb_admin_api` 里 `asyncio.run(sync_local_directory(...))`):上传/sync 的 HTTP 请求会被 parse/chunk/embed 长时间阻塞,重活/崩溃直接波及控制面,也没有重试/串行化语义。本 change 引入**持久 DB 背 job 队列**,把所有 ingest 触发改为"只入队",为后续 `kb-worker`(唯一消费者)铺地基。这是 [target-architecture §12] ingest 目标形态("一个核 + 多触发器 + DB 队列 + 唯一 worker")的第一步。

> 本 change 只建队列 + 入队 + 触发器改造;**消费端(worker)是后续 `kb-worker` change**。本 change 落地后,入队的 job 暂由一个最小内联 drain(或现有同步路径过渡)消费,具体见 design 的过渡方案。

## What Changes

- **新增 `kb_ingest_jobs` 队列表**(管理库,Alembic;与 `scheduled_tasks` 同属编排状态):字段含 `id`、`tenant_id`、`kb_id`、`connector_ref`(非密)、`cred_ref`(Vault 引用,非明文)、`status`(pending/claimed/done/failed)、`attempts`、时间戳。
- **入队 API**:platform 侧提供 enqueue 接口;入队时读 connector 注册表,把**非密 connector 配置 + 凭据 ref**写入 job(不写明文凭据)。
- **触发器改造**:`kb_admin_api` 的 sync/导入端点由"同步 `asyncio.run` 跑 ingest"改为"入队并返回 job id";cron / webhook 触发同样改为入队。
- **claim/done/retry 语义**:队列提供原子 claim(单消费者取一条置 claimed)、done、failed+retry(attempts 上限),保证串行/可重试。
- **过渡消费**:在 `kb-worker` 落地前,提供一个最小的同进程 drain(或保留同步路径作 admin sync 的"入队+等完成"),确保功能不回退。

## Capabilities

### New Capabilities
- `kb-ingest-queue`:持久 DB 背 ingest job 队列 + 入队/claim/done/retry 语义。

### Modified Capabilities
- `kb-admin-api`:sync/导入端点由同步内联 ingest 改为入队返回 job id(admin sync 过渡为"入队+等完成")。

## Impact

**owning package**:`platform/knowledge_base_management`(入队 + 端点改造)、`knowledge_base/ingest`(被入队后调用,不变核逻辑)、迁移(`kb_ingest_jobs` 表)

**public API surface**:`kb_admin_api` sync/导入端点语义变化(返回 job id;admin sync 等完成);新增 enqueue 内部接口

**owned tables**:新增 `kb_ingest_jobs`(管理库,Alembic;**迁移版本号 apply 时取当前 head 续号,勿硬编码**)

**config namespace**:无　**migration**:`kb_ingest_jobs` 表(管理库 Alembic)

**cross-module dependencies**:platform 入队;ingest 核被消费端调用。**队列物理落点(管理库 vs 专用 store)见 design**——worker 经 `db.py` 边界读队列、不 import platform(boundary 不破)。

**与后续 change 关系**:`kb-worker`(消费端,单一 worker)依赖本 change;`connector-cred-job-ref`(凭据 ref 运行时解析)依赖本 change 的 `cred_ref` 字段。
