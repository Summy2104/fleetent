## MODIFIED Requirements

### Requirement: Standalone KB service config contract

KB 服务 standalone 部署 SHALL 从自己的配置文件(`$FLEETENT_HOME/kb-service/kb-service.yaml`)读取 ingest 与检索构造配置:service(tenant_id/host/port)、data(home)、retrieval(default_mode/rerank/top_k)、embedding(endpoint/model/dimensions)、extraction(enabled/endpoint/model)、chunking(chunk_size/chunk_overlap)、connectors(各源 type/kb_id/scope/`sync_interval_seconds`/`credential_ref`)。仓库 SHALL 提供根模板 `kb-service.yaml.example` 与 `kb-service.env.example`；系统 SHALL 提供 `fleetent kb init-config`,从这些 canonical example(经打包资源读取,不依赖 cwd)scaffold `$FLEETENT_HOME/kb-service/` 下的 `kb-service.yaml` 与 `.env`。

#### Scenario: 配置文件驱动连接器
- **WHEN** KB 服务以 standalone 模式启动并加载 `$FLEETENT_HOME/kb-service/kb-service.yaml`
- **THEN** 连接器定义来自该文件,经注入的 settings 提供给 `operations`(不来自 management.db)

#### Scenario: 提供 example 模板与 init-config
- **WHEN** 查看仓库并运行 `fleetent kb init-config`
- **THEN** 存在根 `kb-service.yaml.example` 与 `kb-service.env.example`
- **AND** 命令在 `$FLEETENT_HOME/kb-service/` 生成 `kb-service.yaml` 与 `.env`

#### Scenario: worker 与 serve 共用 kb-service 目录
- **WHEN** `fleetent kb worker --config $FLEETENT_HOME/kb-service/kb-service.yaml` 与 `fleetent kb serve --config $FLEETENT_HOME/kb-service/kb-service.yaml` 启动
- **THEN** 二者共用同一 `kb-service.yaml` 与同目录 `.env`
