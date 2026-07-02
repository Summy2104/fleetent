## MODIFIED Requirements

### Requirement: kb-worker 从专属 .env 加载自身配置

`fleetent kb worker` 启动 SHALL 从每租户 kb home 加载配置:`--config $FLEETENT_HOME/tenants/<tenant>/kb/kb-service.yaml`(构造配置)+ 同目录 `.env`(secrets,经进程环境/`load_dotenv` 提供,connector `credential_ref` / `service_key_ref` 在本地解析)。worker 与 `kb-serve` 共用同一 `tenants/<tenant>/kb/`。worker SHALL 只经 `--config` 加载配置:旧的 tenant-less legacy 兜底(无 `--config` 时读 `$FLEETENT_HOME/kb-service/.env`)**已删除**;旧的 `fleetent kb worker init-config` 与 `kb-worker/.env` 模型(部署级 .env:队列/底座/embedder/Vault)亦**已退役**——由 ``kb-service` `init-config`` + `kb-service.yaml` 取代。

#### Scenario: worker 经 kb-service.yaml 启动
- **WHEN** `fleetent kb worker --config $FLEETENT_HOME/tenants/<tenant>/kb/kb-service.yaml` 启动
- **THEN** worker 从该 yaml 取构造配置、同目录 `.env` 取 secrets,抽 KB 本地队列(`tenants/<tenant>/kb/data/kb_ingest_queue.db`)执行 ingest

#### Scenario: 旧 kb-worker init-config 与 tenant-less 兜底已退役
- **WHEN** 查看 CLI 与 worker 配置加载逻辑
- **THEN** 不再提供 `fleetent kb worker init-config` / `kb-worker.env.example` / `kb-worker/.env`
- **AND** 不再存在读 `$FLEETENT_HOME/kb-service/.env` 的 tenant-less legacy 兜底
- **AND** KB 服务配置由 `fleetent kb init-config` 生成于 `tenants/<tenant>/kb/`
