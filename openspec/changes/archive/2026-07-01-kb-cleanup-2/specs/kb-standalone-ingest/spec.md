## MODIFIED Requirements

### Requirement: KB-local ingest queue, worker and sweep

standalone 模式下,ingest 队列 / worker / sweep SHALL 全在 KB 主机本地:worker 抽 **KB 本地**队列(非 management.db);sweep 由 **kb-worker** 在其抽取循环中按配置文件 `sync_interval_seconds` 到期入队(SHALL NOT 依赖 kb-serve 读服务进程承载调度);**无需 platform 或 management.db**。

队列访问 SHALL 以显式的 queue db url（经 `--config` 解析出的本租户 `kb_ingest_queue.db`）进行;队列访问层 SHALL NOT 在 url 缺失时隐式回落 `management.db`（该表已随 `kb-retire-platform-ingest` 从管理库移除）——缺失/空 url SHALL 以清晰错误失败,不静默指向不存在的管理库表。

standalone KB 服务 SHALL 以**每租户 kb home**部署:`<FLEETENT_HOME>/tenants/<tenant_id>/kb/` 下,`kb-service.yaml` 与 `.env` SHALL 落 `kb/` 根(运维/secret 面);`data.home`(默认 `./data`)SHALL 解析为 `kb/data/`,只表示**当前 tenant 的 sqlite 本地文件后端存储根**,其内部 SHALL 纯平放置 `kb.db`(关系)、`kb_vectors.db`(向量)、`kb_ingest_queue.db`(本地队列),SHALL NOT 在 `data/` 内再嵌套 `tenants/` 或 `kb/` 层。该布局与 agent home(`agents/<id>/agent.yaml` + `.env` + `data/`)同构。多租户 SHALL 通过**不同 tenant kb home 零共享**实现;`tenant_id` 是逻辑身份键,物理由后端实现决定(sqlite=目录;未来 PG=schema、Qdrant=collection)。该 `kb/data/` 即 agent retrieval 读取的同一物理库——service 写的就是 agent 读的。

#### Scenario: 本地队列与 worker
- **WHEN** standalone KB 服务运行 ingest
- **THEN** job 入 KB 主机本地队列(`tenants/<tenant_id>/kb/data/kb_ingest_queue.db`),由本地 worker 抽取执行,写同一 `kb/data/`
- **AND** 不读写 management.db

#### Scenario: 队列访问缺 url 时明确失败不回落管理库
- **WHEN** 队列访问未获得有效 queue db url（缺失或空）
- **THEN** 以清晰错误失败,SHALL NOT 回落到 `management.db`（该表已被移除,回落只会读到不存在的表）

#### Scenario: kb-worker 承载 sweep
- **WHEN** 某连接器配了 `sync_interval_seconds` 且到期
- **THEN** kb-worker 在其抽取循环中入队该连接器同步(不依赖 platform cron,也不依赖 kb-serve 进程)

#### Scenario: 只起 kb-worker 即有调度
- **WHEN** 只启动 kb-worker(未启动 kb-serve)
- **THEN** connector 仍按 `sync_interval_seconds` 被调度入队并抽取执行

#### Scenario: 单租户进程的布局
- **WHEN** 一个 kb-service 进程按 `kb-service.yaml`(单 `service.tenant_id`)启动
- **THEN** 其 `kb.db` / `kb_vectors.db` / `kb_ingest_queue.db` 均位于 `tenants/<tenant_id>/kb/data/` 下;`kb-service.yaml` 与 `.env` 位于 `tenants/<tenant_id>/kb/` 根
- **AND** 另一租户进程使用 `tenants/<other_tenant_id>/kb/`,两者配置、secret 与 sqlite 文件零共享
