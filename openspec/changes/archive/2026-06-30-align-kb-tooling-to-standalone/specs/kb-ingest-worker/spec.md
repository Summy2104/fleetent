## MODIFIED Requirements

### Requirement: kb-worker 从专属 .env 加载自身配置

`fleetent kb worker` 启动 SHALL 从 KB 服务共用的 `kb-service/` 目录加载配置:`--config $FLEETENT_HOME/kb-service/kb-service.yaml`(构造配置)+ 同目录 `.env`(secrets,经进程环境/`load_dotenv` 提供,connector `credential_ref` / `service_key_ref` 在本地解析)。worker 与 `kb-serve` 共用同一 `kb-service/`。旧的 `fleetent kb worker init-config` 与 `kb-worker/.env` 模型(部署级 .env:队列/底座/embedder/Vault)**已退役**——由 ``kb-service` `init-config`` + `kb-service.yaml` 取代。

#### Scenario: worker 经 kb-service.yaml 启动
- **WHEN** `fleetent kb worker --config $FLEETENT_HOME/kb-service/kb-service.yaml` 启动
- **THEN** worker 从该 yaml 取构造配置、同目录 `.env` 取 secrets,抽 KB 本地队列执行 ingest

#### Scenario: 旧 kb-worker init-config 已退役
- **WHEN** 查看 CLI
- **THEN** 不再提供 `fleetent kb worker init-config` / `kb-worker.env.example` / `kb-worker/.env`
- **AND** KB 服务配置由 `fleetent kb init-config` 生成于 `kb-service/`
