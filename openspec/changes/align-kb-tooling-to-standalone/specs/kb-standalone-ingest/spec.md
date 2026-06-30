## ADDED Requirements

### Requirement: kb-service 配置目录布局与 provisioning

KB 服务的配置 SHALL 收于 `$FLEETENT_HOME/kb-service/` 目录:`kb-service.yaml`(非密构造配置)+ `.env`(KB 服务 secrets,如 `KB_SERVICE_KEY`/`KB_CONN_*`/`KB_EMBEDDING_API_KEY`)。该 `.env` SHALL 与 platform 的 `.env` 分开(KB 独立主机只需 `kb-service/` 这一份)。`fleetent kb-serve` 与 `fleetent kb-worker` SHALL 共用同一 `kb-service/`(同一 yaml + 同一 .env)。系统 SHALL 提供 `fleetent kb-service init-config`,从仓库根的 canonical example(`kb-service.yaml.example` + `kb-service.env.example`,经打包资源读取、不依赖 cwd)scaffold `kb-service/`(yaml + .env),幂等(已存在则 skip,`--force` 覆盖)。

#### Scenario: kb-service init-config scaffold 目录
- **WHEN** 运行 `fleetent kb-service init-config`
- **THEN** 在 `$FLEETENT_HOME/kb-service/` 生成 `kb-service.yaml` 与 `.env`(源自根 `kb-service.yaml.example` / `kb-service.env.example`)
- **AND** 已存在时默认 skip,`--force` 时覆盖

#### Scenario: worker 与 serve 共用 kb-service 目录
- **WHEN** `fleetent kb-worker` 与 `fleetent kb-serve` 启动
- **THEN** 二者均从同一 `kb-service/kb-service.yaml` 读配置、同一 `kb-service/.env` 取 secrets

#### Scenario: KB secrets 与 platform 分开
- **WHEN** KB 服务部署于独立主机
- **THEN** 该主机只需 `kb-service/`(yaml + .env),不需要 platform 的 `.env`
