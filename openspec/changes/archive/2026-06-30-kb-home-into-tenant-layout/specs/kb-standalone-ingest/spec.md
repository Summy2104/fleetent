## MODIFIED Requirements

### Requirement: Standalone KB service config contract

KB 服务 standalone 部署 SHALL 从自己的配置文件(`$FLEETENT_HOME/tenants/<tenant_id>/kb/kb-service.yaml`)读取 ingest 与检索构造配置:service(tenant_id/host/port)、data(home)、retrieval(default_mode/rerank/top_k)、embedding(endpoint/model/dimensions)、extraction(enabled/endpoint/model)、chunking(chunk_size/chunk_overlap)、connectors(各源 type/kb_id/scope/`sync_interval_seconds`/`credential_ref`)。仓库 SHALL 提供根模板 `kb-service.yaml.example` 与 `kb-service.env.example`;系统 SHALL 提供 `fleetent kb-service init-config`,从这些 canonical example(经打包资源读取,不依赖 cwd)scaffold `$FLEETENT_HOME/tenants/<tenant_id>/kb/` 下的 `kb-service.yaml` 与 `.env`。

#### Scenario: 配置文件驱动连接器
- **WHEN** KB 服务以 standalone 模式启动并加载 `$FLEETENT_HOME/tenants/<tenant_id>/kb/kb-service.yaml`
- **THEN** 连接器定义来自该文件,经注入的 settings 提供给 `operations`(不来自 management.db)

#### Scenario: 提供 example 模板与 init-config
- **WHEN** 查看仓库并运行 `fleetent kb-service init-config --tenant <tenant_id>`
- **THEN** 存在根 `kb-service.yaml.example` 与 `kb-service.env.example`
- **AND** 命令在 `$FLEETENT_HOME/tenants/<tenant_id>/kb/` 生成 `kb-service.yaml` 与 `.env`

#### Scenario: worker 与 serve 共用 tenant kb home
- **WHEN** `fleetent kb-worker --config $FLEETENT_HOME/tenants/<tenant_id>/kb/kb-service.yaml` 与 `fleetent kb-serve --config $FLEETENT_HOME/tenants/<tenant_id>/kb/kb-service.yaml` 启动
- **THEN** 二者共用同一 `kb-service.yaml` 与同目录 `.env`

### Requirement: KB-local ingest queue, worker and sweep

standalone 模式下,ingest 队列 / worker / sweep SHALL 全在 KB 主机本地:worker 抽 **KB 本地**队列(非 management.db);sweep 由 KB 服务自己的调度器按配置文件 `sync_interval_seconds` 入队;**无需 platform 或 management.db**。

standalone KB 服务 SHALL 以**每租户 kb home**部署:`<FLEETENT_HOME>/tenants/<tenant_id>/kb/` 下,`kb-service.yaml` 与 `.env` SHALL 落 `kb/` 根(运维/secret 面);`data.home`(默认 `./data`)SHALL 解析为 `kb/data/`,只表示**当前 tenant 的 sqlite 本地文件后端存储根**,其内部 SHALL 纯平放置 `kb.db`(关系)、`kb_vectors.db`(向量)、`kb_ingest_queue.db`(本地队列),SHALL NOT 在 `data/` 内再嵌套 `tenants/` 或 `kb/` 层。该布局与 agent home(`agents/<id>/agent.yaml` + `.env` + `data/`)同构。多租户 SHALL 通过**不同 tenant kb home 零共享**实现;`tenant_id` 是逻辑身份键,物理由后端实现决定(sqlite=目录;未来 PG=schema、Qdrant=collection)。该 `kb/data/` 即 agent retrieval 读取的同一物理库——service 写的就是 agent 读的。

#### Scenario: 本地队列与 worker
- **WHEN** standalone KB 服务运行 ingest
- **THEN** job 入 KB 主机本地队列(`tenants/<tenant_id>/kb/data/kb_ingest_queue.db`),由本地 worker 抽取执行,写同一 `kb/data/`
- **AND** 不读写 management.db

#### Scenario: 服务自有 sweep
- **WHEN** 某连接器配了 `sync_interval_seconds` 且到期
- **THEN** KB 服务自己的调度器入队该连接器同步(不依赖 platform cron)

#### Scenario: 单租户进程的布局
- **WHEN** 一个 kb-service 进程按 `kb-service.yaml`(单 `service.tenant_id`)启动
- **THEN** 其 `kb.db` / `kb_vectors.db` / `kb_ingest_queue.db` 均位于 `tenants/<tenant_id>/kb/data/` 下;`kb-service.yaml` 与 `.env` 位于 `tenants/<tenant_id>/kb/` 根
- **AND** 另一租户进程使用 `tenants/<other_tenant_id>/kb/`,两者配置、secret 与 sqlite 文件零共享
