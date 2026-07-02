## MODIFIED Requirements

### Requirement: kb-worker 从专属 .env 加载自身配置

`fleetent kb worker` 默认**单机多租户**,启动 SHALL 从**本机服务级 config** `$FLEETENT_HOME/kb-service.yaml` 加载构造配置(队列/底座/embedding/extraction/共享 service key)。worker SHALL **轮询本机所有在册租户**的 per-tenant 队列(`tenants/<t>/kb/data/kb_ingest_queue.db`,租户经扫 `tenants/*/kb/data/` 发现),认领 job 后按 job.tenant_id 经 `TenantRouter` 写该租户 KB,并**按需加载该租户** connector 配置与 secret(`tenants/<t>/kb/connectors.yaml` + `.env`,connector `credential_ref` 本地解析——仅 connector_sync 类 job 需要)。worker MAY 经 `--tenant <id>` 锁单租户(只从该租户 kb home 加载并只 drain 其队列)。旧的 tenant-less legacy 兜底与 `kb worker init-config` / `kb-worker/.env` 模型仍**已退役**。

#### Scenario: worker 默认多租户加载
- **WHEN** `fleetent kb worker`(默认,读本机 `$FLEETENT_HOME/kb-service.yaml`)启动
- **THEN** worker 从本机 config 取构造配置(含 embedding/共享 service key),轮询所有在册租户队列,按 job.tenant_id 写各租户 `tenants/<t>/kb/data/`
- **AND** 处理某租户 connector_sync 时按需加载该租户 `connectors.yaml` + `.env`,不加载其它租户 secret

#### Scenario: --tenant 锁单租户
- **WHEN** `fleetent kb worker --tenant T` 启动
- **THEN** 只从 `tenants/T/kb/` 加载并只 drain `tenants/T/kb/data/kb_ingest_queue.db`,不碰其它租户

#### Scenario: 旧 init-config 与 tenant-less 兜底仍退役
- **WHEN** 查看 CLI 与 worker 配置加载逻辑
- **THEN** 不提供 `fleetent kb worker init-config` / `kb-worker.env.example` / `kb-worker/.env`
- **AND** 不存在读 `$FLEETENT_HOME/kb-service/.env` 的 tenant-less legacy 兜底
- **AND** 本机服务 config 由 `fleetent kb init-config` 生成于 `$FLEETENT_HOME/kb-service.yaml`,per-tenant connector 于 `tenants/<t>/kb/connectors.yaml`
