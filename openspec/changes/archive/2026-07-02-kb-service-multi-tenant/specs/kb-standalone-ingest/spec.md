## MODIFIED Requirements

### Requirement: Standalone KB service config contract

KB 服务 SHALL 以**两层 config**驱动,默认**单机多租户**:

- **本机服务级 config** `$FLEETENT_HOME/kb-service.yaml`(一份,kb-serve 与 kb-worker 都读):`service`(host/port/**共享 service_key_ref**)、`retrieval`(default_mode/rerank/top_k)、`embedding`(endpoint/model/dimensions,**全机一个模型**)、`extraction`(enabled/endpoint/model)、`chunking`(chunk_size/chunk_overlap)。
- **per-tenant config** `$FLEETENT_HOME/tenants/<tenant_id>/kb/connectors.yaml` + 同目录 `.env`(secret):只含该租户 `connectors`(各源 type/kb_id/scope/`sync_interval_seconds`/`credential_ref`)。
- **租户发现**:服务扫 `$FLEETENT_HOME/tenants/*/kb/data/`(有 `kb.db` 者即在册,动态,新租户 kb home 一建即纳入)。

仓库 SHALL 提供根模板 `kb-service.yaml.example`(本机服务级)与 `kb-service.env.example`;系统 SHALL 提供 `fleetent kb init-config`,生成本机 `kb-service.yaml` 及为已存在租户 scaffold `tenants/<tenant_id>/kb/connectors.yaml` + `.env`。embedding SHALL 全机一个模型:与 per-KB embedding 身份校验相容(所有 KB 同模型);换本机 embedding 模型 SHALL 需 `kb reindex` 重建各 KB 向量。服务 MAY 经 `--tenant <id>` 锁单租户。

#### Scenario: 本机 config 驱动多租户服务
- **WHEN** `fleetent kb serve` / `fleetent kb worker` 以本机 `$FLEETENT_HOME/kb-service.yaml` 启动(默认不锁租户)
- **THEN** 二者读同一本机服务级 config;服务本机所有在册租户,按 principal / job 的 tenant_id 路由到各租户 `tenants/<t>/kb/data/`

#### Scenario: per-tenant 只剩 connectors
- **WHEN** 查看某租户 kb home
- **THEN** `tenants/<t>/kb/connectors.yaml` 只含该租户连接器定义,secret 在同目录 `.env`;service/embedding/rerank 等不再 per-tenant(在本机 config)

#### Scenario: 提供 example 与 init-config
- **WHEN** 运行 `fleetent kb init-config`
- **THEN** 生成本机 `kb-service.yaml`(从根 example),并为已存在租户 scaffold `tenants/<t>/kb/connectors.yaml` + `.env`

### Requirement: KB-local ingest queue, worker and sweep

standalone 模式下 ingest 队列 / worker / sweep SHALL 全在 KB 主机本地(非 management.db)。kb-worker 默认**单机多租户**:SHALL **轮询本机所有在册租户的 per-tenant 队列** `tenants/<t>/kb/data/kb_ingest_queue.db`,认领 job 后按 job 的 tenant_id 经 `TenantRouter` 写该租户 `kb/data/`,并**按需加载该租户** `tenants/<t>/kb/connectors.yaml` + `.env`(connector_sync 才需 secret);sweep 由 kb-worker 在循环中按各租户 connector 的 `sync_interval_seconds` 到期入队(不依赖 kb-serve、不依赖 platform)。worker MAY 经 `--tenant <id>` 只 drain 该租户队列。**单写者纪律不变**:各租户 KB 的内容/向量写仍唯一经 kb-worker。每租户数据 SHALL 物理隔离(独立 `tenants/<t>/kb/data/` SQLite),多租户共享的是进程而非数据。

#### Scenario: 多租户轮询与写
- **WHEN** kb-worker 默认启动,`tenants/A/` 与 `tenants/B/` 各有 pending job
- **THEN** worker 轮询两租户队列、分别认领,按 job.tenant_id 写各自 `tenants/<t>/kb/data/`,互不串写
- **AND** 处理 A 的 connector_sync 时加载 `tenants/A/kb/.env`,不加载 B 的 secret

#### Scenario: 新租户动态纳入
- **WHEN** 运行中新建租户 kb home(`tenants/C/kb/data/kb.db` 出现)
- **THEN** kb-worker 下一轮轮询即纳入租户 C,无需重启

#### Scenario: --tenant 锁单租户
- **WHEN** kb-worker 以 `--tenant A` 启动
- **THEN** 只 drain `tenants/A/kb/data/kb_ingest_queue.db`,不碰其它租户
