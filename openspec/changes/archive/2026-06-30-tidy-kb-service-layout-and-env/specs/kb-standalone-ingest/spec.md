## MODIFIED Requirements

### Requirement: KB-local ingest queue, worker and sweep

standalone 模式下,ingest 队列 / worker / sweep SHALL 全在 KB 主机本地:worker 抽 **KB 本地**队列(非 management.db);sweep 由 KB 服务自己的调度器按配置文件 `sync_interval_seconds` 入队;**无需 platform 或 management.db**。

standalone KB 服务 SHALL 以**每租户自包含 service home**部署:`<FLEETENT_HOME>/kb-service/<tenant_id>/` 下同时包含 `kb-service.yaml`、`.env` 与 `data/`。该 tenant home 下的 `data.home`(默认 `./data`) SHALL 只表示**当前 tenant 的 sqlite 本地文件后端存储根**,其内部 SHALL 纯平放置 `kb.db`(关系)、`kb_vectors.db`(向量)、`kb_ingest_queue.db`(本地队列),SHALL NOT 再出现 `tenants/<tenant_id>/` 或 `kb/` 中间层。多租户 SHALL 通过**不同 tenant home 零共享**实现;`tenant_id` 是逻辑身份键,物理由后端实现决定(sqlite=目录;未来 PG=schema、Qdrant=collection)。嵌入式(agent-home)布局不受影响。

#### Scenario: 本地队列与 worker
- **WHEN** standalone KB 服务运行 ingest
- **THEN** job 入 KB 主机本地队列(`kb-service/<tenant_id>/data/kb_ingest_queue.db`),由本地 worker 抽取执行,写同一 tenant home 的 `data/`
- **AND** 不读写 management.db

#### Scenario: 服务自有 sweep
- **WHEN** 某连接器配了 `sync_interval_seconds` 且到期
- **THEN** KB 服务自己的调度器入队该连接器同步(不依赖 platform cron)

#### Scenario: 单租户进程的扁平布局
- **WHEN** 一个 kb-service 进程按 `kb-service.yaml`(单 `service.tenant_id`)启动
- **THEN** 其 `kb.db` / `kb_vectors.db` / `kb_ingest_queue.db` 均位于 `kb-service/<tenant_id>/data/` 下,无 `tenants/<tenant_id>/`、无 `kb/` 中间层
- **AND** 另一租户进程使用 `kb-service/<other_tenant_id>/data/`,两者配置、secret 与 sqlite 文件零共享

### Requirement: Boot validation of config and credentials

KB 服务启动 SHALL 校验配置完整性:所有连接器引用的 `credential_ref`、以及 embedding / extraction 配置的 `api_key_env`(若设置)所指向的 env/file SHALL 存在;embedding endpoint SHALL 配置;任一缺失 SHALL 启动即失败并指出缺项(不延迟到运行时才炸)。

#### Scenario: 缺凭据启动失败
- **WHEN** 某连接器 `credential_ref`,或 embedding / extraction 的 `api_key_env` 指向的 env/file 不存在
- **THEN** 服务启动失败并报出缺失的引用

#### Scenario: 配置齐全启动成功
- **WHEN** 所有引用就位、embedding 已配
- **THEN** 服务正常启动
